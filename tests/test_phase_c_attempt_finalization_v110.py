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
RUN_ID = "phase-c-finalization-run"
OWNER = "owner-a"
TICKET_ID = "T-1"


def run(*args: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run([*CLI, *args], text=True, capture_output=True)
    if result.returncode != expect:
        raise AssertionError(f"expected {expect}, got {result.returncode}: {result.stdout}\n{result.stderr}")
    return result


def invoke(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([*CLI, *args], text=True, capture_output=True)


def write_json(path: Path, value: Any) -> None:
    ledger.atomic_write(path, ledger.canonical_bytes(value))


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, text=True, capture_output=True).stdout.strip()


class PhaseCAttemptFinalizationTests(unittest.TestCase):
    def init_case(self, root: Path, *, prior_quality: str | None = None) -> dict[str, Any]:
        control, repo = root / "control", root / "repo"
        control.mkdir()
        repo.mkdir()
        subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
        (repo / "app.txt").write_text("baseline\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "app.txt"], check=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "baseline"], check=True)
        baseline_sha = git(repo, "rev-parse", "HEAD")
        baseline_tree = git(repo, "rev-parse", "HEAD^{tree}")
        if prior_quality:
            (repo / "app.txt").write_text("validated candidate\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "app.txt"], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "prior candidate"], check=True)
        run("init", "--control-root", str(control), "--repo-root", str(repo), "--run-id", RUN_ID, "--owner-token", OWNER)
        paths = ledger.paths(control, RUN_ID)
        state, previous = ledger.load_state(paths)
        state.setdefault("attempts", [])
        state.setdefault("issues", [])
        state.setdefault("findings", [])
        state.setdefault("decisions", [])
        state.setdefault("operations", [])
        state.setdefault("candidates", [])
        ticket: dict[str, Any] = {
            "id": TICKET_ID, "goal_ref": "G-1", "criterion_refs": [], "contract_refs": [],
            "dependency_refs": [], "state": "READY", "complexity": "bounded", "risk": "routine",
            "zone": [{"path": "app.txt", "operations": ["modify"]}], "current_attempt": None,
            "current_worker_attempt": None, "last_worker_attempt": None, "current_candidate": None,
            "replacement_refs": [],
        }
        state["tickets"] = [ticket]
        state["lifecycle"] = {
            "phase": "EXECUTE", "control": "ACTIVE", "reason": None, "issue_refs": [], "stop_target": None,
            "next_action": {"kind": "dispatch_ticket", "subject_refs": [TICKET_ID], "preconditions": [], "read_refs": []},
        }
        state["revision"] = 1
        state["previous_publication_hash"] = ledger.sha256_bytes(previous)
        state["repository"].update({"checkout": str(repo), "branch": "main", "initial_head": baseline_sha})

        case: dict[str, Any] = {
            "root": root, "control": control, "repo": repo, "paths": paths,
            "baseline_sha": baseline_sha, "baseline_tree": baseline_tree, "prior_quality": prior_quality,
        }
        if prior_quality:
            candidate_sha = git(repo, "rev-parse", "HEAD")
            candidate_tree = git(repo, "rev-parse", "HEAD^{tree}")
            candidate = self._seed_prior_candidate(case, state, ticket, baseline_sha, baseline_tree, candidate_sha, candidate_tree, prior_quality)
            case.update({"candidate_sha": candidate_sha, "candidate_tree": candidate_tree, "candidate": candidate})
        ledger.validate_ledger(state)
        ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
        install_execution_design(paths, repo)
        state, _ = ledger.load_state(paths)
        state["repository"]["initial_head"] = baseline_sha
        ledger.validate_ledger(state)
        ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
        return case

    def _packet(self, case: dict[str, Any], attempt_id: str, *, base_sha: str | None, mode: str = "implement", repair: dict[str, Any] | None = None) -> dict[str, Any]:
        packet: dict[str, Any] = {
            "identity": {"run_id": RUN_ID, "ticket_id": TICKET_ID, "attempt_id": attempt_id, "epoch": 0},
            "kind": "worker", "mode": mode, "goal": "Phase C finalization regression",
            "acceptance": [{"criterion_id": "C-1"}],
            "workspace": {"root": str(case["repo"]), "expected_base": base_sha},
            "write": {"allow": [{"path": "app.txt", "operations": ["modify"]}]},
            "verification": [{"check_id": "focused", "required": True, "scenario": "focused regression"}],
            "risk": {"level": "routine"}, "context": [{"ref": "contracts/worker.md"}],
            "return_target": {"path": "return.json"},
        }
        state, _ = ledger.load_state(case["paths"])
        if state.get("intent") and state.get("design_publication"):
            intent = ledger.current_intent_binding(state)
            publication = state["design_publication"]
            packet["identity"].update({
                "intent_revision": intent["revision"], "intent_document_ref": intent["document_ref"],
                "intent_document_hash": intent["document_hash"], "design_publication_ref": publication["id"],
                "design_publication_hash": publication["publication_hash"],
                "design_publication_revision": publication["published_revision"], "contract_refs": [],
            })
            packet.update({
                "intent_revision": intent["revision"], "intent_document_ref": intent["document_ref"],
                "intent_document_hash": intent["document_hash"],
            })
        if repair is not None:
            packet["repair"] = repair
        return packet

    def _observe_runtime(
        self, case: dict[str, Any], attempt_id: str, event: str, *,
        descendants: str = "not_applicable", instance: str = "runtime-phase-c",
        return_hash: str | None = None,
    ) -> Path:
        state, _ = ledger.load_state(case["paths"])
        attempt = ledger.attempt_by_id(state, attempt_id)
        event_id = f"OBS-{attempt_id}-{event.upper()}"
        receipt = {
            "kind": "runtime_observation", "event_id": event_id, "event": event,
            "run_id": RUN_ID, "attempt_id": attempt_id, "epoch": attempt["epoch"],
            "packet_hash": attempt["packet_hash"], "spawn_request_id": attempt["runtime"]["spawn_request_id"],
            "runtime_instance_id": instance, "observed_at": "2026-09-18T12:00:00Z",
            "observer": "runtime-adapter-test", "runtime_build": "fixture-1", "return_hash": return_hash,
            "coverage": {"scope": "test process tree", "descendant_writers": descendants},
        }
        receipt_path = case["root"] / f"{event_id}.json"
        write_json(receipt_path, receipt)
        run(
            "observe-runtime", "--control-root", str(case["control"]), "--run-id", RUN_ID,
            "--owner-token", OWNER, "--revision", str(state["revision"]), "--attempt-id", attempt_id,
            "--event", event, "--event-id", event_id, "--event-file", str(receipt_path),
        )
        return receipt_path

    def _seed_prior_candidate(
        self, case: dict[str, Any], state: dict[str, Any], ticket: dict[str, Any],
        baseline_sha: str, baseline_tree: str, candidate_sha: str, candidate_tree: str, quality: str,
    ) -> dict[str, Any]:
        attempt_id = "W-PRIOR"
        packet_hash = "1" * 64
        packet = self._packet(case, attempt_id, base_sha=baseline_sha)
        packet_ref_hash = ledger.object_store(case["paths"], ledger.canonical_bytes(packet))
        returned: dict[str, Any] = {
            "identity": {"run_id": RUN_ID, "ticket_id": TICKET_ID, "attempt_id": attempt_id, "packet_hash": packet_hash, "epoch": 0},
            "status": "DONE" if quality == "DONE" else "BLOCKED",
            "result": "validated candidate", "files": [{"path": "app.txt", "operation": "modify"}],
            "checks": [{"check_id": "focused", "outcome": "pass" if quality == "DONE" else "fail", "actual": "candidate evidence", "evidence_ref": "EV-PRIOR"}],
            "criteria": [{"criterion_id": "C-1", "outcome": "satisfied" if quality == "DONE" else "unsatisfied", "evidence_refs": ["EV-PRIOR"]}],
        }
        if quality == "CONTINUATION":
            returned["issues"] = [{"type": "external_test_fixture_blocker", "cause": "environment", "impact": "blocking", "affected_refs": [TICKET_ID], "expected": "external suite", "actual": "unavailable", "disposition": "retain validated partial work"}]
        return_hash = ledger.object_store(case["paths"], ledger.canonical_bytes(returned))
        attempt: dict[str, Any] = {
            "id": attempt_id, "kind": "worker", "mode": "implement", "subject_ref": TICKET_ID,
            "packet_ref": f"objects/{packet_ref_hash}", "packet_hash": packet_hash, "epoch": 0,
            "state": "RETURNED", "lease": {"id": "L-PRIOR", "state": "released", "zone": [{"path": "app.txt", "operations": ["modify"]}]},
            "route_ref": "route-prior", "checkout": str(case["repo"]), "base_sha": baseline_sha,
            "candidate_sha": candidate_sha, "candidate_tree_sha": candidate_tree,
            "return_ref": f"objects/{return_hash}", "finding_refs": [],
        }
        state["attempts"] = [attempt]
        if quality == "CONTINUATION":
            blocker = {
                "id": "ISS-PRIOR-EXTERNAL", "type": "external_test_fixture_blocker", "cause": "environment",
                "impact": "blocking", "affected_refs": [TICKET_ID, attempt_id], "expected": "external suite available",
                "actual": "fixture unavailable", "disposition": "retain the audited candidate",
                "resolution_condition": "external fixture restored", "source_ref": attempt_id, "invalidated_by": [],
            }
            state["issues"] = [blocker]
            authorization_id = "AUTH-PRIOR-CONT"
            authorization = {
                "id": authorization_id, "type": "continuation_candidate_authorization", "status": "applied",
                "decision": "PRESERVE_CONTINUATION", "reason": "Exact partial work is independently useful.",
                "evidence_refs": [attempt["return_ref"]], "affected_refs": [TICKET_ID, attempt_id],
                "blocker_ref": blocker["id"], "blocker_scope": "external", "external_check_ids": ["focused"],
                "external_criterion_ids": ["C-1"], "invalidated_by": [],
            }
            state["decisions"] = [authorization]
            commit_receipt = {
                "status": "PASS", "checkout": str(case["repo"]), "base_sha": baseline_sha,
                "commit_sha": candidate_sha, "tree_sha": candidate_tree, "authority_ref": authorization_id,
            }
            commit_ref = f"objects/{ledger.object_store(case["paths"], ledger.canonical_bytes(commit_receipt))}"
            audit = {"pass": True, "changed_paths": ["app.txt"]}
            continuation = {
                "run_id": RUN_ID, "ticket_id": TICKET_ID, "attempt_id": attempt_id,
                "return_ref": attempt["return_ref"], "authorization_ref": authorization_id,
                "blocker_ref": blocker["id"], "blocker_scope": "external", "base_sha": baseline_sha,
                "candidate_sha": candidate_sha, "candidate_tree_sha": candidate_tree, "return_status": "BLOCKED",
                "files": returned["files"], "lease_zone": attempt["lease"]["zone"],
                "external_check_ids": ["focused"], "external_criterion_ids": ["C-1"],
                "write_set_audit": audit, "audit_hash": ledger.sha256_bytes(ledger.canonical_bytes(audit)),
                "commit_receipt_ref": commit_ref,
            }
            continuation_ref = f"objects/{ledger.object_store(case["paths"], ledger.canonical_bytes(continuation))}"
            attempt.update({"continuation_ref": continuation_ref, "continuation_authorization_ref": authorization_id})
            state["lifecycle"].update({"control": "BLOCKED", "reason": "blocked_continuation_candidate_preserved", "issue_refs": [blocker["id"]]})
        candidate = ledger.publish_candidate_projection(state, ticket, attempt, quality=quality, blocker_refs=["ISS-PRIOR-EXTERNAL"] if quality == "CONTINUATION" else [])
        ticket.update({"current_attempt": attempt_id, "last_worker_attempt": attempt_id, "current_candidate": candidate["id"], "state": "BLOCKED" if quality == "CONTINUATION" else "CANDIDATE"})
        return candidate

    def seed_terminal(
        self, case: dict[str, Any], *, attempt_id: str = "A-TERMINAL", status: str = "BLOCKED",
        actual_write: bool = False, declared_files: list[dict[str, str]] | None = None, mode: str | None = None,
    ) -> None:
        paths, repo = case["paths"], case["repo"]
        state, previous = ledger.load_state(paths)
        ticket = state["tickets"][0]
        base_sha = case.get("candidate_sha", case["baseline_sha"])
        mode = mode or ("repair" if case.get("prior_quality") else "implement")
        repair: dict[str, Any] | None = None
        if mode == "repair":
            repair = {
                "cause": "implementation", "finding_ref": "ISS-REPAIR", "hypothesis": "repair the current candidate",
                "expected_proof": "focused regression passes", "stopping_condition": "stop after focused proof",
                "causal_change": "correct the failing behavior", "source_attempt_ref": "W-PRIOR",
            }
        packet = self._packet(case, attempt_id, base_sha=base_sha, mode=mode, repair=repair)
        packet_hash = "2" * 64
        packet_ref = f"objects/{ledger.object_store(paths, ledger.canonical_bytes(packet))}"
        issue = {
            "id": "ISS-REPAIR", "type": "implementation_failure", "cause": "implementation", "impact": "blocking",
            "affected_refs": [TICKET_ID, attempt_id], "expected": "verified repair", "actual": status,
            "disposition": "diagnose and authorize a changed repair", "resolution_condition": "fresh proof passes",
            "source_ref": attempt_id, "invalidated_by": [],
        }
        returned: dict[str, Any] = {
            "identity": {"run_id": RUN_ID, "ticket_id": TICKET_ID, "attempt_id": attempt_id, "packet_hash": packet_hash, "epoch": 0},
            "status": status, "result": f"{status} without a new candidate", "files": declared_files or [],
            "checks": [{"check_id": "focused", "outcome": "fail", "actual": "required repair proof failed", "evidence_ref": f"EV-{attempt_id}"}],
            "criteria": [{"criterion_id": "C-1", "outcome": "unsatisfied", "evidence_refs": [f"EV-{attempt_id}"]}],
            "issues": [issue],
        }
        if status == "HANDOFF":
            returned["handoff"] = {"safe_partial_fingerprint": {}, "completed": [], "remaining": ["focused proof"]}
        return_ref = f"objects/{ledger.object_store(paths, ledger.canonical_bytes(returned))}"
        attempt: dict[str, Any] = {
            "id": attempt_id, "kind": "worker", "mode": mode, "subject_ref": TICKET_ID,
            "packet_ref": packet_ref, "packet_hash": packet_hash, "epoch": 0,
            "state": "PREPARED", "lease": {"id": f"L-{attempt_id}", "state": "active", "zone": [{"path": "app.txt", "operations": ["modify"]}]},
            "route_ref": f"route-{attempt_id}", "checkout": str(repo), "base_sha": base_sha,
            "candidate_sha": None, "candidate_tree_sha": None, "return_ref": None, "finding_refs": [],
        }
        ledger.initialize_attempt_runtime(RUN_ID, attempt)
        if repair:
            auth_ref = "AUTH-REPAIR"
            contract_ref = f"objects/{ledger.object_store(paths, ledger.canonical_bytes(repair))}"
            attempt.update({"repair_contract": repair, "repair_authorization_ref": auth_ref, "failure_signature": ledger.repair_signature(repair)})
            state.setdefault("decisions", []).append({
                "id": auth_ref, "type": "repair_authorization", "status": "authorized", "decision": "REPAIR",
                "reason": repair["hypothesis"], "evidence_refs": ["ISS-REPAIR", contract_ref],
                "affected_refs": [TICKET_ID, "ISS-REPAIR"], "intent_revision": None, "invalidated_by": [],
            })
        state.setdefault("issues", []).append(issue)
        if actual_write:
            (repo / "app.txt").write_text("partial owned write\n", encoding="utf-8")
        state["attempts"].append(attempt)
        ticket.update({"state": "BLOCKED", "current_attempt": attempt_id, "last_worker_attempt": attempt_id, "current_worker_attempt": None})
        state["lifecycle"].update({
            "control": "BLOCKED", "reason": f"worker_{status.lower()}", "issue_refs": sorted(set(state["lifecycle"].get("issue_refs", []) + ["ISS-REPAIR"])),
            "next_action": {"kind": "finalize_attempt", "subject_refs": [attempt_id], "preconditions": ["verify stopped writer and exact checkout state"], "read_refs": ["phases/recover.md"]},
        })
        state["revision"] += 1
        state["previous_publication_hash"] = ledger.sha256_bytes(previous)
        ledger.refresh_control_projection(state)
        ledger.validate_ledger(state)
        ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
        self._observe_runtime(case, attempt_id, "start")
        self._observe_runtime(
            case, attempt_id, "return_observed", return_hash=return_ref.removeprefix("objects/"),
        )
        self._observe_runtime(case, attempt_id, "stop", descendants="included")
        state, previous = ledger.load_state(paths)
        terminal_attempt = ledger.attempt_by_id(state, attempt_id)
        terminal_attempt.update({"state": "RETURNED", "return_ref": return_ref})
        state["revision"] += 1
        state["previous_publication_hash"] = ledger.sha256_bytes(previous)
        ledger.refresh_control_projection(state)
        ledger.validate_ledger(state)
        ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))

    def finalize(self, case: dict[str, Any], attempt_id: str, *, expect: int = 0) -> subprocess.CompletedProcess[str]:
        state, _ = ledger.load_state(case["paths"])
        return run(
            "finalize-attempt", "--control-root", str(case["control"]), "--run-id", RUN_ID,
            "--owner-token", OWNER, "--revision", str(state["revision"]), "--ticket-id", TICKET_ID,
            "--attempt-id", attempt_id, expect=expect,
        )

    def test_no_change_repair_restores_done_or_continuation_candidate_for_all_return_outcomes(self) -> None:
        for quality in ("DONE", "CONTINUATION"):
            for status in ("BLOCKED", "HANDOFF", "FAILED"):
                with self.subTest(prior=quality, outcome=status), tempfile.TemporaryDirectory() as directory:
                    case = self.init_case(Path(directory), prior_quality=quality)
                    self.seed_terminal(case, status=status)
                    result = json.loads(self.finalize(case, "A-TERMINAL").stdout)
                    state, _ = ledger.load_state(case["paths"])
                    ticket = state["tickets"][0]
                    attempt = ledger.attempt_by_id(state, "A-TERMINAL")
                    current = ledger.current_candidate_record(state, ticket)
                    self.assertTrue(result["closed"])
                    self.assertEqual("candidate-W-PRIOR", ticket["current_candidate"])
                    self.assertEqual(case["candidate_sha"], current["sha"])
                    self.assertEqual(quality, current["quality"])
                    self.assertEqual("A-TERMINAL", ticket["current_attempt"])
                    self.assertEqual("A-TERMINAL", ticket["last_worker_attempt"])
                    self.assertEqual("released", attempt["lease"]["state"])
                    self.assertIsNone(attempt["candidate_sha"])
                    self.assertEqual("BLOCKED", state["lifecycle"]["control"])

    def test_initial_no_change_terminal_attempt_closes_to_verified_baseline_without_candidate(self) -> None:
        for status in ("BLOCKED", "HANDOFF", "FAILED"):
            with self.subTest(outcome=status), tempfile.TemporaryDirectory() as directory:
                case = self.init_case(Path(directory))
                self.seed_terminal(case, status=status, mode="implement")
                result = json.loads(self.finalize(case, "A-TERMINAL").stdout)
                state, _ = ledger.load_state(case["paths"])
                attempt = ledger.attempt_by_id(state, "A-TERMINAL")
                self.assertTrue(result["closed"])
                self.assertIsNone(state["tickets"][0]["current_candidate"])
                self.assertEqual([], state["candidates"])
                self.assertIsNone(attempt["candidate_sha"])
                self.assertIsNone(attempt["candidate_tree_sha"])
                self.assertEqual("released", attempt["lease"]["state"])
                action = state["lifecycle"]["next_action"]
                self.assertEqual("READY", state["tickets"][0]["state"])
                self.assertEqual("ACTIVE", state["lifecycle"]["control"])
                self.assertEqual("dispatch_ticket", action["kind"])

    def test_stopped_lost_and_interrupted_zero_write_attempts_release_for_retry(self) -> None:
        for terminal_state in ("LOST", "INTERRUPTED"):
            with self.subTest(state=terminal_state), tempfile.TemporaryDirectory() as directory:
                case = self.init_case(Path(directory))
                packet_path = case["root"] / "worker.json"
                write_json(packet_path, self._packet(case, "A-STOPPED", base_sha=case["baseline_sha"]))
                run("dispatch", "--control-root", str(case["control"]), "--run-id", RUN_ID, "--owner-token", OWNER,
                    "--revision", "1", "--ticket-id", TICKET_ID, "--attempt-id", "A-STOPPED", "--lease-id", "L-STOPPED",
                    "--route-id", "route-STOPPED", "--packet", str(packet_path))
                self._observe_runtime(case, "A-STOPPED", "start")
                stop_receipt = self._observe_runtime(case, "A-STOPPED", "stop", descendants="included")
                state, _ = ledger.load_state(case["paths"])
                run("terminate-attempt", "--control-root", str(case["control"]), "--run-id", RUN_ID, "--owner-token", OWNER,
                    "--revision", str(state["revision"]), "--attempt-id", "A-STOPPED", "--state", terminal_state,
                    "--lease-state", "released", "--evidence", str(stop_receipt))
                result = json.loads(self.finalize(case, "A-STOPPED").stdout)
                closed, _ = ledger.load_state(case["paths"])
                self.assertTrue(result["closed"])
                self.assertEqual("released", ledger.attempt_by_id(closed, "A-STOPPED")["lease"]["state"])
                self.assertIsNone(closed["tickets"][0]["current_candidate"])
                self.assertEqual([], closed["candidates"])
                self.assertEqual("READY", closed["tickets"][0]["state"])
                self.assertEqual("ACTIVE", closed["lifecycle"]["control"])
                self.assertEqual("dispatch_ticket", closed["lifecycle"]["next_action"]["kind"])

    def test_unknown_stop_and_foreign_checkout_writes_quarantine_with_exact_recovery_action(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            case = self.init_case(Path(directory))
            packet_path = case["root"] / "worker.json"
            write_json(packet_path, self._packet(case, "A-UNKNOWN", base_sha=case["baseline_sha"]))
            run("dispatch", "--control-root", str(case["control"]), "--run-id", RUN_ID, "--owner-token", OWNER,
                "--revision", "1", "--ticket-id", TICKET_ID, "--attempt-id", "A-UNKNOWN", "--lease-id", "L-UNKNOWN",
                "--route-id", "route-UNKNOWN", "--packet", str(packet_path))
            state, _ = ledger.load_state(case["paths"])
            evidence = case["root"] / "unknown-stop.json"
            write_json(evidence, {"status": "UNKNOWN", "writer_stopped": False, "observation": "timeout without runtime stop receipt"})
            run("terminate-attempt", "--control-root", str(case["control"]), "--run-id", RUN_ID, "--owner-token", OWNER,
                "--revision", str(state["revision"]), "--attempt-id", "A-UNKNOWN", "--state", "LOST",
                "--lease-state", "quarantined", "--evidence", str(evidence))
            state, _ = ledger.load_state(case["paths"])
            self.assertEqual("quarantined", ledger.attempt_by_id(state, "A-UNKNOWN")["lease"]["state"])
            action = state["lifecycle"]["next_action"]
            self.assertEqual("recover_attempt", action["kind"])
            self.assertEqual(["A-UNKNOWN"], action["subject_refs"])
            self.assertTrue(any("reconcile" in item.lower() and "lease" in item.lower() for item in action["preconditions"]))

        with tempfile.TemporaryDirectory() as directory:
            case = self.init_case(Path(directory))
            packet_path = case["root"] / "worker.json"
            write_json(packet_path, self._packet(case, "A-FOREIGN", base_sha=case["baseline_sha"]))
            run("dispatch", "--control-root", str(case["control"]), "--run-id", RUN_ID, "--owner-token", OWNER,
                "--revision", "1", "--ticket-id", TICKET_ID, "--attempt-id", "A-FOREIGN", "--lease-id", "L-FOREIGN",
                "--route-id", "route-FOREIGN", "--packet", str(packet_path))
            self._observe_runtime(case, "A-FOREIGN", "start")
            stop_receipt = self._observe_runtime(case, "A-FOREIGN", "stop", descendants="included")
            (case["repo"] / "foreign.txt").write_text("unowned write\n", encoding="utf-8")
            state, _ = ledger.load_state(case["paths"])
            run("terminate-attempt", "--control-root", str(case["control"]), "--run-id", RUN_ID, "--owner-token", OWNER,
                "--revision", str(state["revision"]), "--attempt-id", "A-FOREIGN", "--state", "INTERRUPTED",
                "--lease-state", "released", "--evidence", str(stop_receipt))
            self.finalize(case, "A-FOREIGN")
            state, _ = ledger.load_state(case["paths"])
            attempt = ledger.attempt_by_id(state, "A-FOREIGN")
            self.assertEqual("quarantined", attempt["lease"]["state"])
            self.assertIsNone(state["tickets"][0]["current_candidate"])
            action = state["lifecycle"]["next_action"]
            self.assertEqual("recover_attempt", action["kind"])
            self.assertEqual(["A-FOREIGN"], action["subject_refs"])
            self.assertTrue(any("foreign" in item.lower() or "write" in item.lower() for item in action["preconditions"]))

    def test_late_stop_and_cleanup_proof_reconciles_quarantine_and_replay_survives_progress(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            case = self.init_case(Path(directory))
            packet_path = case["root"] / "worker.json"
            write_json(packet_path, self._packet(case, "A-QUARANTINED", base_sha=case["baseline_sha"]))
            run("dispatch", "--control-root", str(case["control"]), "--run-id", RUN_ID, "--owner-token", OWNER,
                "--revision", "1", "--ticket-id", TICKET_ID, "--attempt-id", "A-QUARANTINED",
                "--lease-id", "L-QUARANTINED", "--route-id", "route-QUARANTINED", "--packet", str(packet_path))
            unknown = case["root"] / "unknown-stop.json"
            write_json(unknown, {"status": "UNKNOWN", "writer_stopped": False, "observation": "runtime handle was unavailable"})
            state, _ = ledger.load_state(case["paths"])
            run("terminate-attempt", "--control-root", str(case["control"]), "--run-id", RUN_ID, "--owner-token", OWNER,
                "--revision", str(state["revision"]), "--attempt-id", "A-QUARANTINED", "--state", "LOST",
                "--lease-state", "quarantined", "--evidence", str(unknown))
            self.finalize(case, "A-QUARANTINED")
            self._observe_runtime(case, "A-QUARANTINED", "stop", descendants="included", instance="late-runtime")

            failed_proof = case["root"] / "failed-reconciliation.json"
            write_json(failed_proof, {
                "status": "FAIL", "writer_stopped": False, "reconciled": False,
                "disposition": "discarded_to_verified_baseline",
            })
            quarantined, _ = ledger.load_state(case["paths"])
            run(
                "reconcile-finalized-attempt", "--control-root", str(case["control"]), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", str(quarantined["revision"]), "--ticket-id", TICKET_ID,
                "--attempt-id", "A-QUARANTINED", "--evidence", str(failed_proof), expect=2,
            )
            unchanged, _ = ledger.load_state(case["paths"])
            self.assertEqual(quarantined["revision"], unchanged["revision"])
            self.assertEqual("quarantined", ledger.attempt_by_id(unchanged, "A-QUARANTINED")["lease"]["state"])

            proof = case["root"] / "reconciliation.json"
            write_json(proof, {
                "status": "PASS", "writer_stopped": True, "reconciled": True,
                "disposition": "discarded_to_verified_baseline",
                "observation": "late runtime stop proof and exact clean-baseline audit",
            })
            state, _ = ledger.load_state(case["paths"])
            result = json.loads(run(
                "reconcile-finalized-attempt", "--control-root", str(case["control"]), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", str(state["revision"]), "--ticket-id", TICKET_ID,
                "--attempt-id", "A-QUARANTINED", "--evidence", str(proof),
            ).stdout)
            reconciled_revision = result["revision"]
            receipt_ref = result["receipt_ref"]
            state, _ = ledger.load_state(case["paths"])
            attempt = ledger.attempt_by_id(state, "A-QUARANTINED")
            self.assertEqual("released", attempt["lease"]["state"])
            self.assertEqual(receipt_ref, attempt["finalization_reconciliation_ref"])
            self.assertEqual("READY", state["tickets"][0]["state"])
            self.assertEqual("ACTIVE", state["lifecycle"]["control"])
            self.assertEqual("dispatch_ticket", state["lifecycle"]["next_action"]["kind"])

            next_packet = case["root"] / "worker-next.json"
            write_json(next_packet, self._packet(case, "A-NEXT", base_sha=case["baseline_sha"]))
            run("dispatch", "--control-root", str(case["control"]), "--run-id", RUN_ID, "--owner-token", OWNER,
                "--revision", str(reconciled_revision), "--ticket-id", TICKET_ID, "--attempt-id", "A-NEXT",
                "--lease-id", "L-NEXT", "--route-id", "route-NEXT", "--packet", str(next_packet))
            replay = json.loads(run(
                "reconcile-finalized-attempt", "--control-root", str(case["control"]), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", str(reconciled_revision), "--ticket-id", TICKET_ID,
                "--attempt-id", "A-QUARANTINED", "--evidence", str(proof),
            ).stdout)
            progressed, _ = ledger.load_state(case["paths"])
            self.assertTrue(replay["idempotent"])
            self.assertEqual(receipt_ref, replay["receipt_ref"])
            self.assertEqual("A-NEXT", progressed["tickets"][0]["current_attempt"])

    def test_owned_audited_partial_write_never_becomes_done_automatically(self) -> None:
        for status in ("BLOCKED", "HANDOFF"):
            with self.subTest(outcome=status), tempfile.TemporaryDirectory() as directory:
                case = self.init_case(Path(directory), prior_quality="DONE")
                self.seed_terminal(case, status=status, actual_write=True, declared_files=[{"path": "app.txt", "operation": "modify"}])
                result = invoke(
                    "finalize-attempt", "--control-root", str(case["control"]), "--run-id", RUN_ID,
                    "--owner-token", OWNER, "--revision", str(ledger.load_state(case["paths"])[0]["revision"]),
                    "--ticket-id", TICKET_ID, "--attempt-id", "A-TERMINAL",
                )
                self.assertIn(result.returncode, (0, 2), result.stderr)
                self.assertNotIn("invalid choice: 'finalize-attempt'", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                state, _ = ledger.load_state(case["paths"])
                attempt = ledger.attempt_by_id(state, "A-TERMINAL")
                self.assertEqual("candidate-W-PRIOR", state["tickets"][0]["current_candidate"])
                self.assertEqual(case["candidate_sha"], ledger.current_candidate_record(state, state["tickets"][0])["sha"])
                self.assertIsNone(attempt["candidate_sha"])
                self.assertIsNone(attempt["candidate_tree_sha"])
                self.assertFalse(any(item.get("producer_attempt_ref") == "A-TERMINAL" for item in state["candidates"]))
                self.assertNotEqual("DONE", ledger.stored_payload(case["paths"], attempt["return_ref"], "partial return")["status"])

    def test_failed_in_scope_repair_cannot_be_preserved_as_continuation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            case = self.init_case(Path(directory), prior_quality="DONE")
            state, previous = ledger.load_state(case["paths"])
            repo, paths = case["repo"], case["paths"]
            ticket = state["tickets"][0]
            candidate_sha = case["candidate_sha"]
            repair_contract = {
                "cause": "implementation", "finding_ref": "F-REPAIR", "hypothesis": "fix an in-scope defect",
                "expected_proof": "focused check passes", "stopping_condition": "stop after focused check",
                "causal_change": "correct app behavior", "source_attempt_ref": "W-PRIOR",
            }
            review_attempt = {
                "id": "R-PRIOR", "kind": "review", "mode": "change", "subject_ref": TICKET_ID,
                "packet_ref": "objects/" + "3" * 64, "packet_hash": "4" * 64, "epoch": 0,
                "state": "RETURNED", "lease": {"id": "L-R-PRIOR", "state": "released", "zone": []},
                "route_ref": None, "checkout": None, "base_sha": candidate_sha, "candidate_sha": candidate_sha,
                "candidate_tree_sha": case["candidate_tree"], "return_ref": "objects/" + "5" * 64,
                "finding_refs": ["F-REPAIR"], "subject_fingerprint": candidate_sha, "review_result": "BLOCK",
            }
            state["attempts"].append(review_attempt)
            finding = {
                "id": "F-REPAIR", "axis": "correctness", "impact": "blocking", "claim": "in-scope candidate defect",
                "expected": "fixed", "actual": "incorrect", "evidence": "EV-REVIEW", "affected_refs": [TICKET_ID],
                "source_ref": "R-PRIOR", "invalidated_by": [],
            }
            state.setdefault("findings", []).append(finding)
            repair_contract_ref = f"objects/{ledger.object_store(paths, ledger.canonical_bytes(repair_contract))}"
            state.setdefault("decisions", []).append({
                "id": "AUTH-REPAIR", "type": "repair_authorization", "status": "authorized", "decision": "REPAIR",
                "reason": "Bound repair for the current candidate.", "evidence_refs": ["F-REPAIR", repair_contract_ref],
                "affected_refs": [TICKET_ID, "F-REPAIR"], "intent_revision": None, "invalidated_by": [],
            })
            packet = self._packet(case, "A-FAILED-REPAIR", base_sha=candidate_sha, mode="repair", repair=repair_contract)
            packet_hash = "6" * 64
            packet_ref = f"objects/{ledger.object_store(paths, ledger.canonical_bytes(packet))}"
            returned = {
                "identity": {"run_id": RUN_ID, "ticket_id": TICKET_ID, "attempt_id": "A-FAILED-REPAIR", "packet_hash": packet_hash, "epoch": 0},
                "status": "BLOCKED", "result": "in-scope repair check failed", "files": [{"path": "app.txt", "operation": "modify"}],
                "checks": [{"check_id": "focused", "outcome": "fail", "actual": "implementation remains incorrect", "evidence_ref": "EV-FAILED"}],
                "criteria": [{"criterion_id": "C-1", "outcome": "unsatisfied", "evidence_refs": ["EV-FAILED"]}],
                "issues": [{"type": "implementation_failure", "cause": "implementation", "impact": "blocking", "affected_refs": [TICKET_ID], "expected": "fixed", "actual": "still failing", "disposition": "correct implementation"}],
            }
            return_ref = f"objects/{ledger.object_store(paths, ledger.canonical_bytes(returned))}"
            attempt = {
                "id": "A-FAILED-REPAIR", "kind": "worker", "mode": "repair", "subject_ref": TICKET_ID,
                "packet_ref": packet_ref, "packet_hash": packet_hash, "epoch": 0, "state": "RETURNED",
                "lease": {"id": "L-FAILED-REPAIR", "state": "active", "zone": [{"path": "app.txt", "operations": ["modify"]}]},
                "route_ref": "route-failed-repair", "checkout": str(repo), "base_sha": candidate_sha,
                "candidate_sha": None, "candidate_tree_sha": None, "return_ref": return_ref, "finding_refs": [],
                "repair_contract": repair_contract, "repair_authorization_ref": "AUTH-REPAIR",
                "failure_signature": ledger.repair_signature(repair_contract),
            }
            state["attempts"].append(attempt)
            blocker = {
                "id": "ISS-FAILED-REPAIR", "type": "external_test_fixture_blocker", "cause": "environment", "impact": "blocking",
                "affected_refs": [TICKET_ID, "A-FAILED-REPAIR"], "expected": "external check blocked", "actual": "focused required check failed",
                "disposition": "preserve valid partial work only if independent focused proof passes", "source_ref": "A-FAILED-REPAIR", "invalidated_by": [],
            }
            state.setdefault("issues", []).append(blocker)
            authorization = {
                "id": "AUTH-UNSAFE-CONT", "type": "continuation_candidate_authorization", "status": "authorized",
                "decision": "PRESERVE_CONTINUATION", "reason": "Owner claims the focused failure is external.",
                "evidence_refs": [blocker["id"], return_ref], "affected_refs": [TICKET_ID, "A-FAILED-REPAIR"],
                "blocker_ref": blocker["id"], "blocker_scope": "external", "external_check_ids": ["focused"],
                "external_criterion_ids": ["C-1"],
            }
            write_json(case["root"] / "continuation-auth.json", authorization)
            # Create a committed candidate effect to prove that the failed repair still cannot be
            # relabeled as a continuation merely because an owner authorization and commit exist.
            (repo / "app.txt").write_text("still failing\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "app.txt"], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "failed repair"], check=True)
            failed_sha = git(repo, "rev-parse", "HEAD")
            failed_tree = git(repo, "rev-parse", "HEAD^{tree}")
            receipt = {"status": "PASS", "checkout": str(repo), "base_sha": candidate_sha, "commit_sha": failed_sha, "tree_sha": failed_tree, "authority_ref": "AUTH-UNSAFE-CONT"}
            write_json(case["root"] / "commit.json", receipt)
            state["operations"] = [{
                "id": "OP-FAILED-REPAIR", "kind": "candidate_commit", "target": str(repo), "state": "prepared",
                "expected_before": candidate_sha, "intended_after": failed_sha, "authority_ref": "AUTH-UNSAFE-CONT", "receipt_ref": None,
            }]
            ticket.update({"state": "BLOCKED", "current_attempt": "A-FAILED-REPAIR", "last_worker_attempt": "A-FAILED-REPAIR", "current_worker_attempt": None})
            state["lifecycle"].update({"control": "BLOCKED", "reason": "worker_blocked", "issue_refs": [blocker["id"]]})
            state["revision"] += 1
            state["previous_publication_hash"] = ledger.sha256_bytes(previous)
            ledger.refresh_control_projection(state)
            ledger.validate_ledger(state)
            ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
            before_bytes = paths["ledger"].read_bytes()
            rejected = run(
                "preserve-blocked-candidate", "--control-root", str(case["control"]), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", str(state["revision"]), "--ticket-id", TICKET_ID,
                "--attempt-id", "A-FAILED-REPAIR", "--authorization-file", str(case["root"] / "continuation-auth.json"),
                "--commit-receipt", str(case["root"] / "commit.json"), "--operation-id", "OP-FAILED-REPAIR", expect=2,
            )
            self.assertTrue(rejected.stderr)
            after, _ = ledger.load_state(paths)
            self.assertEqual(before_bytes, paths["ledger"].read_bytes())
            self.assertEqual("candidate-W-PRIOR", after["tickets"][0]["current_candidate"])
            self.assertIsNone(ledger.attempt_by_id(after, "A-FAILED-REPAIR")["candidate_sha"])

    def test_exact_closure_replay_is_idempotent_after_a_new_review_is_prepared(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            case = self.init_case(Path(directory), prior_quality="CONTINUATION")
            self.seed_terminal(case, status="HANDOFF")
            first = json.loads(self.finalize(case, "A-TERMINAL").stdout)
            self.assertFalse(first["idempotent"])
            state, _ = ledger.load_state(case["paths"])
            review_packet = {
                "identity": {"run_id": RUN_ID, "attempt_id": "RV-AFTER-CLOSE", "epoch": 0},
                "kind": "review", "mandate": "Review the exact restored continuation candidate.",
                "subject_fingerprint": case["candidate_sha"], "criteria": [{"criterion_id": "C-1"}],
                "axes": ["correctness"], "return_target": {"transport": "file", "path": "review.json"},
            }
            review_path = case["root"] / "review.json"
            write_json(review_path, review_packet)
            run("prepare-review", "--control-root", str(case["control"]), "--run-id", RUN_ID, "--owner-token", OWNER,
                "--revision", str(state["revision"]), "--ticket-id", TICKET_ID, "--review-attempt-id", "RV-AFTER-CLOSE",
                "--lease-id", "L-RV-AFTER-CLOSE", "--packet", str(review_path))
            progressed, _ = ledger.load_state(case["paths"])
            self.assertEqual("PREPARED", ledger.attempt_by_id(progressed, "RV-AFTER-CLOSE")["state"])
            revision = progressed["revision"]
            replay = json.loads(self.finalize(case, "A-TERMINAL").stdout)
            after, _ = ledger.load_state(case["paths"])
            self.assertTrue(replay["idempotent"])
            self.assertEqual(revision, after["revision"])
            self.assertEqual("PREPARED", ledger.attempt_by_id(after, "RV-AFTER-CLOSE")["state"])
            self.assertEqual("candidate-W-PRIOR", after["tickets"][0]["current_candidate"])


if __name__ == "__main__":
    unittest.main()
