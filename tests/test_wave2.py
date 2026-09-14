import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools import ledger


ROOT = Path(__file__).resolve().parents[1]
CLI = ["python3", str(ROOT / "tools" / "ledger.py")]


def run(*args: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run([*CLI, *args], text=True, capture_output=True)
    if result.returncode != expect:
        raise AssertionError(f"expected {expect}, got {result.returncode}: {result.stdout}\n{result.stderr}")
    return result


def write_json(path: Path, value: object) -> None:
    ledger.atomic_write(path, ledger.canonical_bytes(value))


class Wave2Tests(unittest.TestCase):
    def init_run(self, root: Path, run_id: str = "run-2") -> tuple[Path, Path]:
        control = root / "control"
        repo = root / "repo"
        control.mkdir()
        repo.mkdir()
        run("init", "--control-root", str(control), "--repo-root", str(repo), "--run-id", run_id, "--owner-token", "owner-a")
        paths = ledger.paths(control, run_id)
        state, previous = ledger.load_state(paths)
        state["tickets"] = [{"id": "T-1", "goal_ref": "G-1", "criterion_refs": [], "contract_refs": [], "dependency_refs": [], "state": "READY", "complexity": "bounded", "risk": "routine", "zone": [{"path": "app.txt", "operations": ["modify"]}], "current_attempt": None, "replacement_refs": []}]
        state["lifecycle"] = {"phase": "EXECUTE", "control": "ACTIVE", "reason": None, "issue_refs": [], "stop_target": None, "next_action": {"kind": "dispatch", "subject_refs": [], "preconditions": [], "read_refs": []}}
        state["revision"] = 1
        state["previous_publication_hash"] = ledger.sha256_bytes(previous)
        ledger.validate_ledger(state)
        ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
        return control, repo

    def packet(self, run_id: str, attempt_id: str, mode: str = "implement", repair: dict[str, str] | None = None) -> dict[str, object]:
        value: dict[str, object] = {"identity": {"run_id": run_id, "ticket_id": "T-1", "attempt_id": attempt_id, "epoch": 0}, "kind": "worker", "mode": mode, "goal": "wave 2 fixture", "acceptance": [{"criterion_id": "C-1"}], "workspace": {"root": "", "expected_base": None}, "write": {"allow": [{"path": "app.txt", "operations": ["modify"]}]}, "verification": [{"check_id": "oracle", "required": True}], "risk": {"level": "routine"}, "context": [{"ref": "contracts/worker.md"}], "return_target": {"path": "return.json"}}
        if repair is not None:
            value["repair"] = repair
        return value

    def dispatch(self, root: Path, packet: dict[str, object], route: dict[str, object] | None = None, attempt_id: str = "A-1", expect: int = 0, revision: int = 1) -> subprocess.CompletedProcess[str]:
        control = root / "control"
        packet_path = root / f"{attempt_id}-packet.json"
        write_json(packet_path, packet)
        args = ["dispatch", "--control-root", str(control), "--run-id", "run-2", "--owner-token", "owner-a", "--revision", str(revision), "--ticket-id", "T-1", "--attempt-id", attempt_id, "--lease-id", f"L-{attempt_id}", "--route-id", f"route-{attempt_id}", "--packet", str(packet_path)]
        if route is not None:
            route_path = root / f"{attempt_id}-route.json"
            write_json(route_path, route)
            args += ["--route", str(route_path)]
        return run(*args, expect=expect)

    def test_rejected_or_unknown_route_cannot_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_run(root)
            route = {"id": "route-A-1", "capability": "worker", "reasoning": "standard", "adequacy": "REJECTED", "context_grade": "UNKNOWN", "fallback_cause": "permission"}
            result = self.dispatch(root, self.packet("run-2", "A-1"), route, expect=2)
            self.assertIn("not eligible", result.stderr)
            state, _ = ledger.load_state(ledger.paths(root / "control", "run-2"))
            self.assertEqual("READY", state["tickets"][0]["state"])

    def test_block_return_and_findings_are_durable_and_not_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_run(root)
            self.dispatch(root, self.packet("run-2", "A-1"))
            paths = ledger.paths(root / "control", "run-2")
            state, _ = ledger.load_state(paths)
            payload = {"identity": {"run_id": "run-2", "ticket_id": "T-1", "attempt_id": "A-1", "packet_hash": state["attempts"][0]["packet_hash"], "epoch": 0}, "status": "BLOCKED", "result": "contract is incomplete", "files": [], "checks": [{"check_id": "oracle", "outcome": "not_run", "actual": "blocked", "evidence_ref": "ev-block"}], "criteria": [{"criterion_id": "C-1", "outcome": "unverifiable", "evidence_refs": ["ev-block"]}], "issues": [{"type": "contract_gap", "cause": "contract", "impact": "blocking", "affected_refs": ["T-1"], "disposition": "repair contract"}]}
            inbox = paths["scratch"] / "A-1" / "return.json"
            write_json(inbox, payload)
            run("ingest-return", "--control-root", str(root / "control"), "--run-id", "run-2", "--owner-token", "owner-a", "--revision", "2", "--attempt-id", "A-1", "--return-file", str(inbox), "--kind", "worker")
            state, _ = ledger.load_state(paths)
            self.assertEqual("BLOCKED", state["lifecycle"]["control"])
            self.assertEqual("BLOCKED", state["tickets"][0]["state"])
            self.assertTrue(any(issue["cause"] == "contract" for issue in state["issues"]))
            self.assertGreater(state["usage"]["counters"]["return_bytes"], 0)
            receipt = root / "commit.json"
            write_json(receipt, {"status": "PASS", "commit_sha": "0" * 40, "tree_sha": "1" * 40})
            result = run("candidate", "--control-root", str(root / "control"), "--run-id", "run-2", "--owner-token", "owner-a", "--revision", "3", "--attempt-id", "A-1", "--commit-receipt", str(receipt), "--operation-id", "missing", expect=2)
            self.assertIn("DONE", result.stderr)

    def test_done_return_outside_lease_is_quarantined_and_not_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_run(root)
            self.dispatch(root, self.packet("run-2", "A-1"))
            paths = ledger.paths(root / "control", "run-2")
            state, _ = ledger.load_state(paths)
            payload = {"identity": {"run_id": "run-2", "ticket_id": "T-1", "attempt_id": "A-1", "packet_hash": state["attempts"][0]["packet_hash"], "epoch": 0}, "status": "DONE", "result": "updated", "files": [{"path": "other.txt", "operation": "modify"}], "checks": [{"check_id": "oracle", "outcome": "pass", "actual": "ok", "evidence_ref": "ev-worker"}], "criteria": [{"criterion_id": "C-1", "outcome": "satisfied", "evidence_refs": ["ev-worker"]}]}
            inbox = paths["scratch"] / "A-1" / "return.json"
            write_json(inbox, payload)

            result = run("ingest-return", "--control-root", str(root / "control"), "--run-id", "run-2", "--owner-token", "owner-a", "--revision", "2", "--attempt-id", "A-1", "--return-file", str(inbox), "--kind", "worker")

            self.assertIn('"status": "BLOCKED"', result.stdout)
            state, _ = ledger.load_state(paths)
            attempt = state["attempts"][0]
            self.assertEqual("quarantined", attempt["lease"]["state"])
            self.assertEqual("BLOCKED", state["lifecycle"]["control"])
            self.assertEqual("BLOCKED", state["tickets"][0]["state"])
            issue = next(issue for issue in state["issues"] if issue["type"] == "write_set_violation")
            self.assertEqual("ownership", issue["cause"])
            self.assertIn("other.txt", issue["actual"])

            receipt = root / "commit.json"
            write_json(receipt, {"status": "PASS", "commit_sha": "0" * 40, "tree_sha": "1" * 40})
            candidate = run("candidate", "--control-root", str(root / "control"), "--run-id", "run-2", "--owner-token", "owner-a", "--revision", "3", "--attempt-id", "A-1", "--commit-receipt", str(receipt), "--operation-id", "missing", expect=2)
            self.assertIn("active, non-quarantined worker lease", candidate.stderr)

    def test_amendment_records_full_consumer_closure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, _ = self.init_run(root)
            paths = ledger.paths(control, "run-2")
            old_path = paths["docs"] / "intent" / "v1.md"
            ledger.atomic_write(old_path, b"old intent\n")
            state, previous = ledger.load_state(paths)
            state.update({"documents": [{"id": "D-1", "version": "v1", "path": str(old_path), "hash": ledger.sha256_file(old_path), "kind": "intent", "section_anchors": []}], "intent": {"current_revision": "v1", "document_ref": "D-1", "approved_amendments": []}, "requirements": [{"id": "R-1", "version": "v1", "status": "active", "provenance_refs": ["D-1"], "criterion_refs": ["C-1"]}], "criteria": [{"id": "C-1", "version": "v1", "requirement_refs": ["R-1"], "oracle": "fixture", "status": "active"}], "contracts": [{"id": "K-1", "version": "v1", "status": "active", "provenance_refs": ["D-1"]}]})
            state["revision"] = 1; state["previous_publication_hash"] = ledger.sha256_bytes(previous)
            ledger.validate_ledger(state); ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
            new_intent = root / "new.md"; new_intent.write_text("new intent\n", encoding="utf-8")
            run("amend", "--control-root", str(control), "--run-id", "run-2", "--owner-token", "owner-a", "--revision", "1", "--intent-file", str(new_intent), "--doc-id", "D-2", "--doc-version", "v2", "--intent-revision", "v2", "--amendment-id", "AM-1", "--authority-ref", "user")
            state, _ = ledger.load_state(paths)
            invalidation = state["invalidations"][0]
            self.assertIn("T-1", invalidation["consumer_refs"])
            self.assertIn("R-1", invalidation["consumer_refs"])
            self.assertIn("C-1", invalidation["consumer_refs"])
            self.assertIn("K-1", invalidation["consumer_refs"])
            self.assertIn("AM-1", state["tickets"][0]["invalidated_by"])
            self.assertEqual("STALE", state["tickets"][0]["state"])
            self.assertEqual(ledger.sha256_file(paths["docs"] / "D-2" / "v2.md"), state["intent"]["document_hash"])

    def test_usage_publication_is_attributable_and_null_tokens_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); control, _ = self.init_run(root)
            event = root / "usage.json"
            write_json(event, {"id": "U-1", "kind": "g5_manual", "actor": "orchestrator", "subject_ref": "A-G5", "scope": "shared_setup", "delta": {"orchestrator_turns": 1, "wait_calls": 2, "manual_setup": 1, "manual_wait": 1, "packet_bytes": 128}, "evidence": [{"id": "EV-U-1", "hash": "a" * 64, "outcome": "observed", "observer": "test", "scenario": "setup"}]})
            run("publish-usage", "--control-root", str(control), "--run-id", "run-2", "--owner-token", "owner-a", "--revision", "1", "--event-file", str(event))
            state, _ = ledger.load_state(ledger.paths(control, "run-2"))
            self.assertIsNone(state["usage"]["tokens"])
            self.assertEqual("token_meter_unavailable", state["usage"]["token_reason"])
            self.assertEqual(2, state["usage"]["counters"]["wait_calls"])
            self.assertEqual(2, state["usage"]["shared_setup"]["wait_calls"])
            self.assertTrue(any(e["id"] == "EV-U-1" for e in state["evidence"]))
            brief = json.loads(run("brief", "--control-root", str(control), "--run-id", "run-2").stdout)
            self.assertIn("usage", brief); self.assertIn("findings", brief); self.assertIn("intent", brief)

    def test_reviewer_disagreement_is_durably_adjudicated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); control, _ = self.init_run(root)
            paths = ledger.paths(control, "run-2")
            state, previous = ledger.load_state(paths)
            state["reviews"] = [{"id": "REV-PASS", "mandate": "change", "subject_fingerprint": "candidate", "verdict": "PASS", "return_ref": "objects/" + "a" * 64, "context_refs": ["clean"], "finding_refs": []}, {"id": "REV-BLOCK", "mandate": "change", "subject_fingerprint": "candidate", "verdict": "BLOCK", "return_ref": "objects/" + "b" * 64, "context_refs": ["clean"], "finding_refs": []}]
            state["issues"] = [{"id": "ISS-DISAGREE", "type": "reviewer_disagreement", "cause": "oracle", "impact": "blocking", "affected_refs": ["T-1", "REV-PASS", "REV-BLOCK"], "disposition": "adjudication required"}]
            state["lifecycle"]["control"] = "BLOCKED"; state["lifecycle"]["issue_refs"] = ["ISS-DISAGREE"]; state["revision"] = 1; state["previous_publication_hash"] = ledger.sha256_bytes(previous)
            ledger.validate_ledger(state); ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
            decision = root / "decision.json"
            write_json(decision, {"id": "ADJ-1", "type": "reviewer_adjudication", "status": "resolved", "decision": "PASS", "reason": "independent evidence resolves the factual disagreement", "evidence_refs": ["ev-independent"], "affected_refs": ["REV-PASS", "REV-BLOCK", "T-1"], "supersedes": ["REV-PASS", "REV-BLOCK"]})
            run("adjudicate", "--control-root", str(control), "--run-id", "run-2", "--owner-token", "owner-a", "--revision", "1", "--decision-file", str(decision))
            state, _ = ledger.load_state(paths)
            self.assertEqual("ADJ-1", state["decisions"][0]["id"])
            self.assertEqual("ACTIVE", state["lifecycle"]["control"])
            self.assertNotIn("ISS-DISAGREE", state["lifecycle"]["issue_refs"])

    def test_repair_packet_requires_contract_and_rejects_same_signature(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); control, _ = self.init_run(root)
            paths = ledger.paths(control, "run-2")
            state, previous = ledger.load_state(paths)
            state["findings"] = [{"id": "F-1", "axis": "correctness", "impact": "blocking", "claim": "fixture defect", "expected": "fixed", "actual": "broken", "evidence": "ev-1", "affected_refs": ["T-1"], "source_ref": "T-1"}]
            state["revision"] = 1; state["previous_publication_hash"] = ledger.sha256_bytes(previous)
            ledger.validate_ledger(state); ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
            repair = {"cause": "implementation", "finding_ref": "F-1", "hypothesis": "the branch condition is inverted", "expected_proof": "regression test observes the corrected branch", "stopping_condition": "stop when the regression remains green", "causal_change": "invert branch condition"}
            self.dispatch(root, self.packet("run-2", "A-1", mode="repair", repair=repair), attempt_id="A-1")
            state, _ = ledger.load_state(paths); state["tickets"][0]["state"] = "READY"; state["revision"] += 1; state["previous_publication_hash"] = ledger.sha256_bytes(paths["ledger"].read_bytes()); ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
            result = self.dispatch(root, self.packet("run-2", "A-2", mode="repair", repair=repair), attempt_id="A-2", expect=2, revision=3)
            self.assertIn("unchanged repair retry", result.stderr)


if __name__ == "__main__":
    unittest.main()
