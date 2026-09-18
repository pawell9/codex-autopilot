from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tools import ledger
from tests.test_phase_b_projections_v110 import install_execution_design


ROOT = Path(__file__).resolve().parents[1]
CLI = ["python3", str(ROOT / "tools" / "ledger.py")]
RUN_ID = "continuation-run"
TICKET_ID = "T-1"
ATTEMPT_ID = "A-1"
OWNER = "owner-a"


def run(*args: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run([*CLI, *args], text=True, capture_output=True)
    if result.returncode != expect:
        raise AssertionError(f"expected {expect}, got {result.returncode}: {result.stdout}\n{result.stderr}")
    return result


def write_json(path: Path, value: object) -> None:
    ledger.atomic_write(path, ledger.canonical_bytes(value))


class BlockedContinuationCandidateTests(unittest.TestCase):
    def prepare_case(
        self,
        root: Path,
        *,
        focused_outcome: str = "pass",
        declared_path: str = "app.txt",
        extra_committed_path: bool = False,
        return_status: str = "BLOCKED",
    ) -> dict[str, Any]:
        control = root / "control"
        repo = root / "repo"
        control.mkdir()
        repo.mkdir()
        run("init", "--control-root", str(control), "--repo-root", str(repo), "--run-id", RUN_ID, "--owner-token", OWNER)
        (repo / "app.txt").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
        subprocess.run(["git", "-C", str(repo), "add", "app.txt"], check=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "base"], check=True)
        base_sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, text=True, capture_output=True).stdout.strip()

        paths = ledger.paths(control, RUN_ID)
        state, previous = ledger.load_state(paths)
        state["tickets"] = [{
            "id": TICKET_ID, "goal_ref": "G-1", "criterion_refs": [], "contract_refs": [],
            "dependency_refs": [], "state": "READY", "complexity": "bounded", "risk": "routine",
            "zone": [{"path": "app.txt", "operations": ["modify"]}], "current_attempt": None,
            "replacement_refs": [],
        }]
        state["lifecycle"] = {"phase": "EXECUTE", "control": "ACTIVE", "reason": None, "issue_refs": [], "stop_target": None,
                              "next_action": {"kind": "dispatch", "subject_refs": [], "preconditions": [], "read_refs": []}}
        state["revision"] = 1
        state["previous_publication_hash"] = ledger.sha256_bytes(previous)
        state["repository"].update({"checkout": str(repo), "branch": "main", "initial_head": base_sha})
        ledger.validate_ledger(state)
        ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
        install_execution_design(paths, repo)
        state, _ = ledger.load_state(paths)
        state["repository"]["initial_head"] = base_sha
        ledger.validate_ledger(state)
        ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))

        packet = {
            "identity": {"run_id": RUN_ID, "ticket_id": TICKET_ID, "attempt_id": ATTEMPT_ID, "epoch": 0},
            "kind": "worker", "mode": "implement", "goal": "continuation candidate fixture",
            "acceptance": [{"criterion_id": "C-1"}],
            "workspace": {"root": str(repo), "expected_base": base_sha},
            "write": {"allow": [{"path": "app.txt", "operations": ["modify"]}]},
            "verification": [
                {"check_id": "TICKET-FOCUSED", "required": True, "scenario": "focused ticket regressions"},
                {"check_id": "OFFLINE-SUITE", "required": True, "scenario": "complete offline suite"},
                {"check_id": "TICKET-LINT", "required": True, "scenario": "ticket lint"},
            ],
            "risk": {"level": "routine"}, "context": [{"ref": "contracts/worker.md"}],
            "return_target": {"path": "return.json"},
        }
        intent = ledger.current_intent_binding(state)
        publication = state["design_publication"]
        packet["identity"].update({
            "intent_revision": intent["revision"], "intent_document_ref": intent["document_ref"],
            "intent_document_hash": intent["document_hash"], "design_publication_ref": publication["id"],
            "design_publication_hash": publication["publication_hash"],
            "design_publication_revision": publication["published_revision"], "contract_refs": [],
        })
        packet.update({"intent_revision": intent["revision"], "intent_document_ref": intent["document_ref"],
                       "intent_document_hash": intent["document_hash"]})
        packet_path = root / "packet.json"
        write_json(packet_path, packet)
        run("dispatch", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
            "--revision", "1", "--ticket-id", TICKET_ID, "--attempt-id", ATTEMPT_ID,
            "--lease-id", "L-1", "--route-id", "route-1", "--packet", str(packet_path))
        state, _ = ledger.load_state(paths)
        attempt = ledger.attempt_by_id(state, ATTEMPT_ID)
        for event, event_id, descendants in (("start", "OBS-WORKER-START", "not_applicable"), ("stop", "OBS-WORKER-STOP", "included")):
            observation = {
                "kind": "runtime_observation", "event_id": event_id, "event": event,
                "run_id": RUN_ID, "attempt_id": ATTEMPT_ID, "epoch": attempt["epoch"],
                "packet_hash": attempt["packet_hash"], "spawn_request_id": attempt["runtime"]["spawn_request_id"],
                "runtime_instance_id": "runtime-continuation-worker", "observed_at": "2026-09-18T12:00:00Z",
                "observer": "runtime-adapter-test", "runtime_build": "fixture-1", "return_hash": None,
                "coverage": {"scope": "test process tree", "descendant_writers": descendants},
            }
            observation_path = root / f"{event_id}.json"
            write_json(observation_path, observation)
            run("observe-runtime", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
                "--revision", str(state["revision"]), "--attempt-id", ATTEMPT_ID, "--event", event,
                "--event-id", event_id, "--event-file", str(observation_path))
            state, _ = ledger.load_state(paths)
        worker_return = {
            "identity": {**packet["identity"], "packet_hash": attempt["packet_hash"]},
            "status": return_status, "result": "focused work is complete; the full suite has an external resource blocker",
            "files": [{"path": declared_path, "operation": "modify"}],
            "checks": [
                {"check_id": "TICKET-FOCUSED", "outcome": focused_outcome, "actual": "focused checks", "evidence_ref": "ev-focused"},
                {"check_id": "OFFLINE-SUITE", "outcome": "fail", "actual": "authoritative suite inputs are absent from the exact base", "evidence_ref": "ev-suite"},
                {"check_id": "TICKET-LINT", "outcome": "pass", "actual": "lint passes", "evidence_ref": "ev-lint"},
            ],
            "criteria": [{"criterion_id": "C-1", "outcome": "unsatisfied", "evidence_refs": ["ev-suite"]}],
            "issues": [{
                "type": "external_test_fixture_blocker", "cause": "environment", "impact": "blocking",
                "affected_refs": [TICKET_ID, "OFFLINE-SUITE"],
                "expected": "The complete offline suite passes.",
                "actual": "Authoritative external suite resources are absent from the exact base and outside this lease.",
                "disposition": "Preserve the in-scope work; do not broaden the ticket lease.",
                "resolution_condition": "Restore authoritative suite resources outside this ticket or rerun in a qualified environment.",
            }],
        }
        if return_status == "HANDOFF":
            worker_return["handoff"] = {"safe_partial_fingerprint": {"app.txt": "partial"}, "completed": ["focused work"], "remaining": ["external suite"]}
        inbox = paths["scratch"] / ATTEMPT_ID / "return.json"
        write_json(inbox, worker_return)
        run("ingest-return", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
            "--revision", str(state["revision"]), "--attempt-id", ATTEMPT_ID, "--return-file", str(inbox), "--kind", "worker")
        state, _ = ledger.load_state(paths)
        blocker = next(item for item in state["issues"] if item["type"] == "external_test_fixture_blocker")
        auth_id = "AUTH-CONT-1"
        run("prepare-effect", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
            "--revision", str(state["revision"]), "--operation-id", "OP-CONT-1", "--kind", "candidate_commit",
            "--target", str(repo), "--expected-before", base_sha, "--authority-ref", auth_id)

        (repo / "app.txt").write_text("candidate\n", encoding="utf-8")
        if extra_committed_path:
            (repo / "outside.txt").write_text("not in lease\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "outside.txt"], check=True)
        subprocess.run(["git", "-C", str(repo), "add", "app.txt"], check=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "continuation candidate"], check=True)
        candidate_sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, text=True, capture_output=True).stdout.strip()
        tree_sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD^{tree}"], check=True, text=True, capture_output=True).stdout.strip()
        commit_receipt = root / "commit.json"
        write_json(commit_receipt, {"status": "PASS", "run_id": RUN_ID, "ticket_id": TICKET_ID,
                                    "attempt_id": ATTEMPT_ID, "operation_id": "OP-CONT-1", "kind": "candidate_commit",
                                    "target": str(repo), "checkout": str(repo), "expected_before": base_sha,
                                    "base_sha": base_sha, "intended_after": candidate_sha,
                                    "commit_sha": candidate_sha, "tree_sha": tree_sha, "authority_ref": auth_id})
        auth = {
            "id": auth_id, "type": "continuation_candidate_authorization", "status": "authorized",
            "decision": "PRESERVE_CONTINUATION",
            "reason": "The failed complete-suite check is caused by proven external resources absent from the exact base.",
            "evidence_refs": [blocker["id"], state["attempts"][0]["return_ref"]],
            "affected_refs": [TICKET_ID, ATTEMPT_ID], "blocker_ref": blocker["id"],
            "blocker_scope": "external", "external_check_ids": ["OFFLINE-SUITE"],
            "external_criterion_ids": ["C-1"],
        }
        auth_path = root / "authorization.json"
        write_json(auth_path, auth)
        return {"root": root, "control": control, "repo": repo, "paths": paths, "base_sha": base_sha,
                "candidate_sha": candidate_sha, "tree_sha": tree_sha, "commit_receipt": commit_receipt,
                "authorization_path": auth_path, "authorization": auth, "blocker": blocker, "packet": packet}

    def preserve(self, case: dict[str, Any], *, revision: int | None = None, expect: int = 0) -> subprocess.CompletedProcess[str]:
        state, _ = ledger.load_state(case["paths"])
        return run("preserve-blocked-candidate", "--control-root", str(case["control"]), "--run-id", RUN_ID,
                   "--owner-token", OWNER, "--revision", str(state["revision"] if revision is None else revision),
                   "--ticket-id", TICKET_ID, "--attempt-id", ATTEMPT_ID,
                   "--authorization-file", str(case["authorization_path"]),
                   "--commit-receipt", str(case["commit_receipt"]), "--operation-id", "OP-CONT-1", expect=expect)

    def test_preserves_exact_blocked_write_set_and_allows_review_and_repair(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            case = self.prepare_case(Path(directory))
            result = json.loads(self.preserve(case).stdout)
            state, _ = ledger.load_state(case["paths"])
            attempt = ledger.attempt_by_id(state, ATTEMPT_ID)
            ticket = next(item for item in state["tickets"] if item["id"] == TICKET_ID)
            receipt = ledger.stored_payload(case["paths"], attempt["continuation_ref"], "test continuation")
            self.assertEqual(case["candidate_sha"], result["candidate"])
            self.assertEqual("BLOCKED", state["lifecycle"]["control"])
            self.assertEqual("BLOCKED", ticket["state"])
            self.assertEqual("BLOCKED", ledger.stored_payload(case["paths"], attempt["return_ref"], "test return")["status"])
            self.assertTrue(receipt["write_set_audit"]["pass"])
            self.assertEqual(["app.txt"], receipt["write_set_audit"]["changed_paths"])
            self.assertEqual(case["candidate_sha"], receipt["candidate_sha"])
            self.assertEqual("applied", next(item for item in state["decisions"] if item["id"] == "AUTH-CONT-1")["status"])
            self.assertEqual("blocking", next(item for item in state["issues"] if item["id"] == case["blocker"]["id"])["impact"])
            self.assertEqual("worker_blocked", state["lifecycle"]["reason"])
            self.assertEqual("BLOCKED", ledger.validated_candidate_worker_return(case["paths"], state, ticket, attempt)["status"])
            repeated = json.loads(self.preserve(case).stdout)
            self.assertTrue(repeated["idempotent"])
            self.assertEqual(state["revision"], ledger.load_state(case["paths"])[0]["revision"])

            review_packet = {
                "identity": {"run_id": RUN_ID, "attempt_id": "RV-1", "epoch": 0}, "kind": "review",
                "mandate": "Review this blocked continuation candidate for concrete implementation defects.",
                "subject_fingerprint": case["candidate_sha"], "criteria": [{"criterion_id": "C-1"}],
                "axes": ["correctness"], "return_target": {"transport": "file", "path": "review.json"},
            }
            review_path = case["root"] / "review-packet.json"
            write_json(review_path, review_packet)
            run("prepare-review", "--control-root", str(case["control"]), "--run-id", RUN_ID, "--owner-token", OWNER,
                "--revision", str(state["revision"]), "--ticket-id", TICKET_ID, "--review-attempt-id", "RV-1",
                "--lease-id", "RL-1", "--packet", str(review_path))
            state, _ = ledger.load_state(case["paths"])
            review_attempt = ledger.attempt_by_id(state, "RV-1")
            for event, event_id, descendants in (("start", "OBS-REVIEW-START", "not_applicable"), ("stop", "OBS-REVIEW-STOP", "included")):
                observation = {
                    "kind": "runtime_observation", "event_id": event_id, "event": event,
                    "run_id": RUN_ID, "attempt_id": "RV-1", "epoch": review_attempt["epoch"],
                    "packet_hash": review_attempt["packet_hash"], "spawn_request_id": review_attempt["runtime"]["spawn_request_id"],
                    "runtime_instance_id": "runtime-continuation-review", "observed_at": "2026-09-18T12:00:00Z",
                    "observer": "runtime-adapter-test", "runtime_build": "fixture-1", "return_hash": None,
                    "coverage": {"scope": "test process tree", "descendant_writers": descendants},
                }
                observation_path = case["root"] / f"{event_id}.json"
                write_json(observation_path, observation)
                run("observe-runtime", "--control-root", str(case["control"]), "--run-id", RUN_ID,
                    "--owner-token", OWNER, "--revision", str(state["revision"]), "--attempt-id", "RV-1",
                    "--event", event, "--event-id", event_id, "--event-file", str(observation_path))
                state, _ = ledger.load_state(case["paths"])
            self.assertEqual("BLOCKED", state["lifecycle"]["control"])
            self.assertEqual("BLOCKED", next(item for item in state["tickets"] if item["id"] == TICKET_ID)["state"])
            integrity_path = case["root"] / "integrity.json"
            write_json(integrity_path, {"status": "PASS", "candidate_fingerprint": case["candidate_sha"]})
            blocked_integrate = run("integrate", "--control-root", str(case["control"]), "--run-id", RUN_ID,
                                    "--owner-token", OWNER, "--revision", str(state["revision"]),
                                    "--attempt-id", "RV-1", "--review-file", str(case["root"] / "missing-review.json"),
                                    "--integrity-receipt", str(integrity_path), "--review-id", "REV-1", expect=2)
            self.assertIn("continuation-only candidate cannot be integrated", blocked_integrate.stderr)

            review_attempt = ledger.attempt_by_id(state, "RV-1")
            review_return = {
                "identity": {"run_id": RUN_ID, "attempt_id": "RV-1", "packet_hash": review_attempt["packet_hash"], "epoch": 0},
                "subject_fingerprint": case["candidate_sha"], "verdict": "BLOCK",
                "coverage": [{"criterion_id": "C-1", "outcome": "partial", "evidence_refs": ["ev-review"]}],
                "checks": [{"check_id": "correctness", "axis": "correctness", "outcome": "failed", "actual": "fixture finding", "evidence_ref": "ev-review"}],
                "context_refs": ["clean-review-context"], "findings": [],
            }
            review_inbox = case["paths"]["scratch"] / "RV-1" / "return.json"
            write_json(review_inbox, review_return)
            run("ingest-return", "--control-root", str(case["control"]), "--run-id", RUN_ID, "--owner-token", OWNER,
                "--revision", str(state["revision"]), "--attempt-id", "RV-1", "--return-file", str(review_inbox), "--kind", "review")
            state, _ = ledger.load_state(case["paths"])
            review_issue = next(item for item in state["issues"] if item["type"] == "review_verdict" and TICKET_ID in item["affected_refs"] and not item.get("invalidated_by"))
            repair = {"cause": "implementation", "finding_ref": review_issue["id"], "hypothesis": "A fresh review found a candidate-bound issue.",
                      "expected_proof": "A regression test observes the correction.", "stopping_condition": "Stop when the focused regression passes.",
                      "causal_change": "Correct only the reviewed app behavior."}
            repair_path = case["root"] / "repair.json"
            write_json(repair_path, repair)
            run("authorize-repair", "--control-root", str(case["control"]), "--run-id", RUN_ID, "--owner-token", OWNER,
                "--revision", str(state["revision"]), "--ticket-id", TICKET_ID, "--finding-ref", review_issue["id"],
                "--authorization-id", "AUTH-REPAIR-1", "--repair-contract", str(repair_path))
            state, _ = ledger.load_state(case["paths"])
            self.assertEqual("BLOCKED", state["lifecycle"]["control"])
            self.assertEqual("READY", next(item for item in state["tickets"] if item["id"] == TICKET_ID)["state"])
            repair_packet = dict(case["packet"])
            repair_packet["identity"] = {**case["packet"]["identity"], "attempt_id": "A-2"}
            repair_packet["mode"] = "repair"
            repair_packet["workspace"] = {"root": str(case["repo"]), "expected_base": case["candidate_sha"]}
            repair_packet["repair"] = repair
            repair_packet_path = case["root"] / "repair-packet.json"
            write_json(repair_packet_path, repair_packet)
            run("dispatch", "--control-root", str(case["control"]), "--run-id", RUN_ID, "--owner-token", OWNER,
                "--revision", str(state["revision"]), "--ticket-id", TICKET_ID, "--attempt-id", "A-2",
                "--lease-id", "L-A-2", "--route-id", "route-A-2", "--packet", str(repair_packet_path))
            state, _ = ledger.load_state(case["paths"])
            self.assertEqual("BLOCKED", state["lifecycle"]["control"])
            self.assertEqual("RUNNING", next(item for item in state["tickets"] if item["id"] == TICKET_ID)["state"])

    def test_rejects_worker_owned_failed_required_check_without_publication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            case = self.prepare_case(Path(directory), focused_outcome="fail")
            before, raw = ledger.load_state(case["paths"])
            result = self.preserve(case, expect=2)
            after, _ = ledger.load_state(case["paths"])
            self.assertIn("no own failures", result.stderr)
            self.assertEqual(before["revision"], after["revision"])
            self.assertEqual(raw, case["paths"]["ledger"].read_bytes())
            self.assertIsNone(ledger.attempt_by_id(after, ATTEMPT_ID).get("continuation_ref"))

    def test_rejects_actual_write_set_outside_ticket_lease(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            case = self.prepare_case(Path(directory), extra_committed_path=True)
            before, _ = ledger.load_state(case["paths"])
            result = self.preserve(case, expect=2)
            after, _ = ledger.load_state(case["paths"])
            self.assertIn("continuation write-set audit failed", result.stderr)
            self.assertEqual(before["revision"], after["revision"])
            self.assertEqual("BLOCKED", after["lifecycle"]["control"])
            self.assertIsNone(ledger.attempt_by_id(after, ATTEMPT_ID).get("continuation_ref"))

    def test_rejects_quarantined_lease_and_corrupt_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = self.prepare_case(root, declared_path="outside.txt")
            before, _ = ledger.load_state(case["paths"])
            result = self.preserve(case, expect=2)
            after, _ = ledger.load_state(case["paths"])
            self.assertIn("active, non-quarantined lease", result.stderr)
            self.assertEqual("quarantined", ledger.attempt_by_id(after, ATTEMPT_ID)["lease"]["state"])
            self.assertEqual(before["revision"], after["revision"])

        with tempfile.TemporaryDirectory() as directory:
            case = self.prepare_case(Path(directory))
            state, previous = ledger.load_state(case["paths"])
            ledger.attempt_by_id(state, ATTEMPT_ID)["repair_lease_provenance"] = {
                "authorization_ref": "AUTH-FAKE", "finding_ref": "F-FAKE", "source_attempt_ref": "A-FAKE",
                "candidate_sha": "b" * 40, "packet_base_sha": "b" * 40,
                "expanded_entries": [{"path": "app.txt", "operations": ["modify"]}],
                "lineage": [{"path": "app.txt", "attempts": [{"attempt_ref": "A-FAKE", "ticket_ref": TICKET_ID,
                    "base_sha": "a" * 40, "candidate_sha": "b" * 40, "return_ref": "objects/" + "c" * 64, "operation": "create"}]}],
            }
            state["revision"] += 1
            state["previous_publication_hash"] = ledger.sha256_bytes(previous)
            ledger.validate_ledger(state)
            ledger.atomic_write(case["paths"]["ledger"], ledger.canonical_bytes(state))
            result = self.preserve(case, expect=2)
            after, _ = ledger.load_state(case["paths"])
            self.assertIn("non-repair continuation attempt contains repair provenance", result.stderr)
            self.assertEqual("BLOCKED", after["lifecycle"]["control"])
            self.assertIsNone(ledger.attempt_by_id(after, ATTEMPT_ID).get("continuation_ref"))

    def test_handoff_can_be_preserved_without_changing_its_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            case = self.prepare_case(Path(directory), return_status="HANDOFF")
            self.preserve(case)
            state, _ = ledger.load_state(case["paths"])
            attempt = ledger.attempt_by_id(state, ATTEMPT_ID)
            returned = ledger.stored_payload(case["paths"], attempt["return_ref"], "test handoff")
            self.assertEqual("HANDOFF", returned["status"])
            self.assertEqual("BLOCKED", state["lifecycle"]["control"])
            self.assertEqual("BLOCKED", next(item for item in state["tickets"] if item["id"] == TICKET_ID)["state"])

    def test_repair_candidate_revalidates_transitive_create_to_modify_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control = root / "control"
            repo = root / "repo"
            control.mkdir()
            repo.mkdir()
            run("init", "--control-root", str(control), "--repo-root", str(repo), "--run-id", RUN_ID, "--owner-token", OWNER)
            subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "--allow-empty", "-qm", "base"], check=True)
            source_base = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, text=True, capture_output=True).stdout.strip()
            (repo / "app.txt").write_text("created\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "app.txt"], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "create candidate"], check=True)
            source_candidate = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, text=True, capture_output=True).stdout.strip()
            source_tree = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD^{tree}"], check=True, text=True, capture_output=True).stdout.strip()

            paths = ledger.paths(control, RUN_ID)
            state, previous = ledger.load_state(paths)
            ticket = {"id": TICKET_ID, "goal_ref": "G-1", "criterion_refs": [], "contract_refs": [], "dependency_refs": [],
                      "state": "BLOCKED", "complexity": "bounded", "risk": "routine", "zone": [{"path": "app.txt", "operations": ["create"]}],
                      "current_attempt": "A-repair", "replacement_refs": []}
            source_return = {
                "identity": {"run_id": RUN_ID, "ticket_id": TICKET_ID, "attempt_id": "A-create", "packet_hash": "1" * 64, "epoch": 0},
                "status": "DONE", "result": "created app", "files": [{"path": "app.txt", "operation": "create"}],
                "checks": [{"check_id": "focused", "outcome": "pass", "actual": "pass", "evidence_ref": "ev-create"}],
                "criteria": [{"criterion_id": "C-1", "outcome": "satisfied", "evidence_refs": ["ev-create"]}],
            }
            source_packet = {"identity": {"run_id": RUN_ID, "ticket_id": TICKET_ID, "attempt_id": "A-create", "epoch": 0},
                             "kind": "worker", "mode": "implement", "goal": "create", "acceptance": [{"criterion_id": "C-1"}],
                             "workspace": {"root": str(repo), "expected_base": source_base},
                             "write": {"allow": [{"path": "app.txt", "operations": ["create"]}]},
                             "verification": [{"check_id": "focused", "required": True}], "risk": {"level": "routine"},
                             "context": [{"ref": "contracts/worker.md"}], "return_target": {"path": "return.json"}}
            source_return_ref = f"objects/{ledger.object_store(paths, ledger.canonical_bytes(source_return))}"
            source_packet_ref = f"objects/{ledger.object_store(paths, ledger.canonical_bytes(source_packet))}"
            repair = {"cause": "implementation", "finding_ref": "F-1", "hypothesis": "A current review found the create-only path needs a narrow correction.",
                      "expected_proof": "A focused test proves the correction.", "stopping_condition": "Stop when the focused check passes.",
                      "causal_change": "Modify only app.txt.", "source_attempt_ref": "A-create"}
            repair_contract_ref = f"objects/{ledger.object_store(paths, ledger.canonical_bytes(repair))}"
            attempt_packet = {
                "identity": {"run_id": RUN_ID, "ticket_id": TICKET_ID, "attempt_id": "A-repair", "epoch": 0},
                "kind": "worker", "mode": "repair", "goal": "modify app", "acceptance": [{"criterion_id": "C-1"}],
                "workspace": {"root": str(repo), "expected_base": source_candidate},
                "write": {"allow": [{"path": "app.txt", "operations": ["modify"]}]},
                "verification": [{"check_id": "TICKET-FOCUSED", "required": True, "scenario": "focused ticket regressions"},
                                 {"check_id": "OFFLINE-SUITE", "required": True, "scenario": "complete offline suite"},
                                 {"check_id": "TICKET-LINT", "required": True, "scenario": "ticket lint"}],
                "risk": {"level": "routine"}, "context": [{"ref": "contracts/worker.md"}],
                "return_target": {"path": "return.json"}, "repair": repair,
            }
            repair_return = {
                "identity": {"run_id": RUN_ID, "ticket_id": TICKET_ID, "attempt_id": "A-repair", "packet_hash": "2" * 64, "epoch": 0},
                "status": "BLOCKED", "result": "focused work passed; external full-suite resources are absent",
                "files": [{"path": "app.txt", "operation": "modify"}],
                "checks": [{"check_id": "TICKET-FOCUSED", "outcome": "pass", "actual": "focused test passes", "evidence_ref": "ev-focused"},
                           {"check_id": "OFFLINE-SUITE", "outcome": "fail", "actual": "external suite resource absent", "evidence_ref": "ev-suite"},
                           {"check_id": "TICKET-LINT", "outcome": "pass", "actual": "lint passes", "evidence_ref": "ev-lint"}],
                "criteria": [{"criterion_id": "C-1", "outcome": "unsatisfied", "evidence_refs": ["ev-suite"]}],
                "issues": [{"type": "external_test_fixture_blocker", "cause": "environment", "impact": "blocking",
                            "affected_refs": [TICKET_ID, "OFFLINE-SUITE"], "expected": "Full suite passes", "actual": "External source files are absent outside the ticket lease.",
                            "disposition": "Do not widen lease.", "resolution_condition": "Restore external source files or qualify the suite environment."}],
            }
            (repo / "app.txt").write_text("repair candidate\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "app.txt"], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "blocked continuation"], check=True)
            candidate_sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, text=True, capture_output=True).stdout.strip()
            candidate_tree = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD^{tree}"], check=True, text=True, capture_output=True).stdout.strip()
            repair_return_ref = f"objects/{ledger.object_store(paths, ledger.canonical_bytes(repair_return))}"
            attempt_packet_ref = f"objects/{ledger.object_store(paths, ledger.canonical_bytes(attempt_packet))}"
            state.update({
                "revision": 1, "previous_publication_hash": ledger.sha256_bytes(previous), "tickets": [ticket],
                "repository": {**state["repository"], "checkout": str(repo), "branch": "main", "initial_head": source_base},
                "attempts": [
                    {"id": "A-create", "kind": "worker", "mode": "implement", "subject_ref": TICKET_ID, "packet_ref": source_packet_ref,
                     "packet_hash": "1" * 64, "epoch": 0, "state": "RETURNED", "lease": {"id": "L-create", "state": "released", "zone": [{"path": "app.txt", "operations": ["create"]}]},
                     "checkout": str(repo), "base_sha": source_base, "candidate_sha": source_candidate, "candidate_tree_sha": source_tree,
                     "return_ref": source_return_ref, "finding_refs": []},
                    {"id": "A-review", "kind": "review", "mode": "change", "subject_ref": TICKET_ID, "packet_ref": None, "packet_hash": None,
                     "epoch": 0, "state": "RETURNED", "lease": {"id": "L-review", "state": "released", "zone": []},
                     "candidate_sha": source_candidate, "subject_fingerprint": source_candidate, "finding_refs": ["F-1"]},
                    {"id": "A-repair", "kind": "worker", "mode": "repair", "subject_ref": TICKET_ID, "packet_ref": attempt_packet_ref,
                     "packet_hash": "2" * 64, "epoch": 0, "state": "RETURNED", "lease": {"id": "L-repair", "state": "active", "zone": [{"path": "app.txt", "operations": ["modify"]}]},
                     "checkout": str(repo), "base_sha": source_candidate, "candidate_sha": None, "candidate_tree_sha": None,
                     "return_ref": repair_return_ref, "finding_refs": ["ISS-EXT"], "repair_contract": repair, "repair_authorization_ref": "AUTH-REPAIR",
                     "repair_lease_provenance": {"authorization_ref": "AUTH-REPAIR", "finding_ref": "F-1", "source_attempt_ref": "A-create",
                         "candidate_sha": source_candidate, "packet_base_sha": source_candidate,
                         "expanded_entries": [{"path": "app.txt", "operations": ["modify"]}],
                         "lineage": [{"path": "app.txt", "attempts": [{"attempt_ref": "A-create", "ticket_ref": TICKET_ID,
                             "base_sha": source_base, "candidate_sha": source_candidate, "return_ref": source_return_ref, "operation": "create"}]}]},
                    },
                ],
                "findings": [{"id": "F-1", "axis": "correctness", "impact": "blocking", "claim": "candidate issue", "expected": "fixed", "actual": "broken",
                              "evidence": "review evidence", "affected_refs": [TICKET_ID], "source_ref": "A-review", "invalidated_by": []}],
                "decisions": [{"id": "AUTH-REPAIR", "type": "repair_authorization", "status": "authorized", "decision": "REPAIR",
                               "reason": "review repair", "evidence_refs": ["F-1", repair_contract_ref], "affected_refs": [TICKET_ID, "F-1"], "invalidated_by": []}],
                "issues": [{"id": "ISS-EXT", "type": "external_test_fixture_blocker", "cause": "environment", "impact": "blocking",
                            "affected_refs": [TICKET_ID, "OFFLINE-SUITE"], "actual": "external suite inputs missing", "expected": "full suite passes",
                            "disposition": "preserve candidate", "source_ref": "A-repair", "invalidated_by": []}],
                "operations": [{"id": "OP-CONT", "kind": "candidate_commit", "target": str(repo), "state": "prepared",
                                "expected_before": source_candidate, "intended_after": None, "authority_ref": "AUTH-CONT", "receipt_ref": None}],
                "lifecycle": {"phase": "EXECUTE", "control": "BLOCKED", "reason": "worker_blocked", "issue_refs": ["ISS-EXT"], "stop_target": None,
                              "next_action": {"kind": "triage_or_repair", "subject_refs": ["A-repair"], "preconditions": [], "read_refs": []}},
            })
            ledger.validate_ledger(state)
            ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
            commit_receipt = root / "commit.json"
            write_json(commit_receipt, {"status": "PASS", "run_id": RUN_ID, "ticket_id": TICKET_ID,
                                        "attempt_id": "A-repair", "operation_id": "OP-CONT", "kind": "candidate_commit",
                                        "target": str(repo), "checkout": str(repo), "expected_before": source_candidate,
                                        "base_sha": source_candidate, "intended_after": candidate_sha,
                                        "commit_sha": candidate_sha, "tree_sha": candidate_tree, "authority_ref": "AUTH-CONT"})
            authorization = {"id": "AUTH-CONT", "type": "continuation_candidate_authorization", "status": "authorized",
                             "decision": "PRESERVE_CONTINUATION", "reason": "The full-suite failure is an external resource blocker.",
                             "evidence_refs": ["ISS-EXT", repair_return_ref], "affected_refs": [TICKET_ID, "A-repair"],
                             "blocker_ref": "ISS-EXT", "blocker_scope": "external", "external_check_ids": ["OFFLINE-SUITE"],
                             "external_criterion_ids": ["C-1"]}
            auth_path = root / "authorization.json"
            write_json(auth_path, authorization)
            result = run("preserve-blocked-candidate", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
                         "--revision", "1", "--ticket-id", TICKET_ID, "--attempt-id", "A-repair",
                         "--authorization-file", str(auth_path), "--commit-receipt", str(commit_receipt), "--operation-id", "OP-CONT")
            self.assertIn(candidate_sha, result.stdout)
            final, _ = ledger.load_state(paths)
            continuation = ledger.attempt_by_id(final, "A-repair")["continuation_ref"]
            self.assertTrue(ledger.stored_payload(paths, continuation, "continuation receipt")["write_set_audit"]["pass"])


if __name__ == "__main__":
    unittest.main()
