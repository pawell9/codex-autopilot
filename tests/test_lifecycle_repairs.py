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


class LifecycleRepairTests(unittest.TestCase):
    def init_ticket(self, root: Path, *, operation: str = "modify") -> tuple[Path, Path, dict[str, Path]]:
        control, repo = root / "control", root / "repo"
        control.mkdir(); repo.mkdir()
        run("init", "--control-root", str(control), "--repo-root", str(repo), "--run-id", "repair-run", "--owner-token", "owner-a")
        paths = ledger.paths(control, "repair-run")
        state, previous = ledger.load_state(paths)
        state["tickets"] = [{"id": "T-1", "goal_ref": "G-1", "criterion_refs": [], "contract_refs": [], "dependency_refs": [], "state": "READY", "complexity": "bounded", "risk": "routine", "zone": [{"path": "app.txt", "operations": [operation]}], "current_attempt": None, "replacement_refs": []}]
        state["lifecycle"] = {"phase": "EXECUTE", "control": "ACTIVE", "reason": None, "issue_refs": [], "stop_target": None, "next_action": {"kind": "dispatch", "subject_refs": ["T-1"], "preconditions": [], "read_refs": []}}
        state["revision"] = 1
        state["previous_publication_hash"] = ledger.sha256_bytes(previous)
        ledger.validate_ledger(state)
        ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
        return control, repo, paths

    def worker_packet(self, root: Path, attempt_id: str, *, mode: str = "implement", base: str | None = None, path: str = "app.txt", operation: str = "modify", repair: dict[str, object] | None = None) -> Path:
        packet = {
            "identity": {"run_id": "repair-run", "ticket_id": "T-1", "attempt_id": attempt_id, "epoch": 0},
            "kind": "worker", "mode": mode, "goal": "lifecycle regression",
            "acceptance": [{"criterion_id": "C-1"}],
            "workspace": {"root": str(root / "repo"), "expected_base": base},
            "write": {"allow": [{"path": path, "operations": [operation]}]},
            "verification": [{"check_id": "oracle", "required": True}],
            "risk": {"level": "routine"}, "context": [{"ref": "contracts/worker.md"}],
            "return_target": {"path": "return.json"},
        }
        if repair is not None:
            packet["repair"] = repair
        packet_path = root / f"{attempt_id}.json"
        write_json(packet_path, packet)
        return packet_path

    def dispatch(self, control: Path, packet: Path, attempt_id: str, revision: int, *, expect: int = 0) -> subprocess.CompletedProcess[str]:
        return run("dispatch", "--control-root", str(control), "--run-id", "repair-run", "--owner-token", "owner-a", "--revision", str(revision), "--ticket-id", "T-1", "--attempt-id", attempt_id, "--lease-id", f"L-{attempt_id}", "--route-id", f"route-{attempt_id}", "--packet", str(packet), expect=expect)

    def seed_create_candidate_finding(self, root: Path, *, source_attempt_ref: str | None = "A-create") -> tuple[Path, dict[str, Path], str]:
        control, _, paths = self.init_ticket(root, operation="create")
        candidate = "b" * 40
        prior_return = {
            "identity": {"run_id": "repair-run", "ticket_id": "T-1", "attempt_id": "A-create", "packet_hash": "1" * 64, "epoch": 0},
            "status": "DONE", "result": "created app.txt", "files": [{"path": "app.txt", "operation": "create"}],
            "checks": [{"check_id": "oracle", "outcome": "pass", "actual": "created", "evidence_ref": "EV-create"}],
            "criteria": [{"criterion_id": "C-1", "outcome": "satisfied", "evidence_refs": ["EV-create"]}],
        }
        prior_digest = ledger.object_store(paths, ledger.canonical_bytes(prior_return))
        state, previous = ledger.load_state(paths)
        state["attempts"] = [
            {"id": "A-create", "kind": "worker", "mode": "implement", "subject_ref": "T-1", "packet_ref": "objects/" + "2" * 64, "packet_hash": "1" * 64, "epoch": 0, "state": "RETURNED", "lease": {"id": "L-create", "state": "released", "zone": [{"path": "app.txt", "operations": ["create"]}]}, "route_ref": "route-create", "checkout": str(root / "repo"), "base_sha": "a" * 40, "candidate_sha": candidate, "candidate_tree_sha": "c" * 40, "return_ref": f"objects/{prior_digest}", "finding_refs": []},
            {"id": "A-review", "kind": "review", "mode": "change", "subject_ref": "T-1", "packet_ref": "objects/" + "3" * 64, "packet_hash": "4" * 64, "epoch": 0, "state": "RETURNED", "lease": {"id": "L-review", "state": "released", "zone": []}, "route_ref": None, "checkout": None, "base_sha": candidate, "candidate_sha": candidate, "candidate_tree_sha": "c" * 40, "return_ref": "objects/" + "5" * 64, "finding_refs": ["F-1"], "subject_fingerprint": candidate, "review_result": "BLOCK"},
        ]
        state["findings"] = [{"id": "F-1", "axis": "correctness", "impact": "blocking", "claim": "created file needs correction", "expected": "correct", "actual": "incorrect", "evidence": "EV-review", "affected_refs": ["T-1"], "source_ref": "A-review", "intent_revision": None, "repair_contract_ref": None, "invalidated_by": []}]
        state["tickets"][0]["state"] = "REVIEW"
        state["tickets"][0]["current_attempt"] = "A-create"
        state["lifecycle"]["control"] = "BLOCKED"
        state["lifecycle"]["reason"] = "review_not_pass"
        state["revision"] = 2
        state["previous_publication_hash"] = ledger.sha256_bytes(previous)
        ledger.validate_ledger(state)
        ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
        repair = {"cause": "implementation", "finding_ref": "F-1", "hypothesis": "created content is wrong", "expected_proof": "regression observes corrected content", "stopping_condition": "stop after the focused regression passes", "causal_change": "replace the generated value", "source_attempt_ref": source_attempt_ref}
        repair_path = root / "repair-contract.json"; write_json(repair_path, repair)
        run("authorize-repair", "--control-root", str(control), "--run-id", "repair-run", "--owner-token", "owner-a", "--revision", "2", "--ticket-id", "T-1", "--finding-ref", "F-1", "--authorization-id", "AUTH-1", "--repair-contract", str(repair_path))
        return control, paths, candidate

    def test_dispatch_return_ingest_is_internal_and_advances_without_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); control, _, paths = self.init_ticket(root)
            packet = self.worker_packet(root, "A-1")
            self.dispatch(control, packet, "A-1", 1)
            waiting, _ = ledger.load_state(paths)
            self.assertEqual("ACTIVE", waiting["lifecycle"]["control"])
            self.assertEqual("await_worker_return", waiting["lifecycle"]["next_action"]["kind"])
            self.assertIn("not a user checkpoint", " ".join(waiting["lifecycle"]["next_action"]["preconditions"]))
            attempt = ledger.attempt_by_id(waiting, "A-1")
            returned = {"identity": {"run_id": "repair-run", "ticket_id": "T-1", "attempt_id": "A-1", "packet_hash": attempt["packet_hash"], "epoch": 0}, "status": "DONE", "result": "modified", "files": [{"path": "app.txt", "operation": "modify"}], "checks": [{"check_id": "oracle", "outcome": "pass", "actual": "ok", "evidence_ref": "EV"}], "criteria": [{"criterion_id": "C-1", "outcome": "satisfied", "evidence_refs": ["EV"]}]}
            inbox = paths["scratch"] / "A-1" / "return.json"; write_json(inbox, returned)
            run("validate-return", "--control-root", str(control), "--run-id", "repair-run", "--attempt-id", "A-1", "--return-file", str(inbox), "--kind", "worker")
            run("ingest-return", "--control-root", str(control), "--run-id", "repair-run", "--owner-token", "owner-a", "--revision", "2", "--attempt-id", "A-1", "--return-file", str(inbox), "--kind", "worker")
            ingested, _ = ledger.load_state(paths)
            self.assertEqual("ACTIVE", ingested["lifecycle"]["control"])
            self.assertEqual("audit_worker_return_and_prepare_candidate", ingested["lifecycle"]["next_action"]["kind"])

    def test_lost_worker_has_bounded_recovery_without_releasing_unproven_writer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); control, _, paths = self.init_ticket(root)
            self.dispatch(control, self.worker_packet(root, "A-lost"), "A-lost", 1)
            evidence = root / "timeout.json"; write_json(evidence, {"status": "UNKNOWN", "writer_stopped": False, "observation": "three no-progress wait intervals"})
            run("terminate-attempt", "--control-root", str(control), "--run-id", "repair-run", "--owner-token", "owner-a", "--revision", "2", "--attempt-id", "A-lost", "--state", "LOST", "--lease-state", "quarantined", "--evidence", str(evidence))
            state, _ = ledger.load_state(paths)
            self.assertEqual("BLOCKED", state["lifecycle"]["control"])
            self.assertEqual("recover_attempt", state["lifecycle"]["next_action"]["kind"])
            self.assertEqual("quarantined", ledger.attempt_by_id(state, "A-lost")["lease"]["state"])

    def test_same_ticket_create_candidate_repair_modify_is_proven_and_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); control, paths, candidate = self.seed_create_candidate_finding(root)
            repair = json.loads((root / "repair-contract.json").read_text(encoding="utf-8"))
            packet = self.worker_packet(root, "A-repair", mode="repair", base=candidate, repair=repair)
            self.dispatch(control, packet, "A-repair", 3)
            state, _ = ledger.load_state(paths)
            attempt = ledger.attempt_by_id(state, "A-repair")
            self.assertEqual([{"path": "app.txt", "operations": ["modify"]}], attempt["lease"]["zone"])
            self.assertEqual("A-create", attempt["repair_lease_provenance"]["source_attempt_ref"])
            returned = {"identity": {"run_id": "repair-run", "ticket_id": "T-1", "attempt_id": "A-repair", "packet_hash": attempt["packet_hash"], "epoch": 0}, "status": "DONE", "result": "repaired", "files": [{"path": "app.txt", "operation": "modify"}], "checks": [{"check_id": "oracle", "outcome": "pass", "actual": "fixed", "evidence_ref": "EV-repair"}], "criteria": [{"criterion_id": "C-1", "outcome": "satisfied", "evidence_refs": ["EV-repair"]}]}
            inbox = paths["scratch"] / "A-repair" / "return.json"; write_json(inbox, returned)
            result = run("ingest-return", "--control-root", str(control), "--run-id", "repair-run", "--owner-token", "owner-a", "--revision", "4", "--attempt-id", "A-repair", "--return-file", str(inbox), "--kind", "worker")
            self.assertFalse(json.loads(result.stdout)["quarantined"])
            final, _ = ledger.load_state(paths)
            self.assertEqual("active", ledger.attempt_by_id(final, "A-repair")["lease"]["state"])

    def test_repair_modify_rejects_stale_foreign_and_missing_provenance(self) -> None:
        cases = {
            "stale": {"base": "d" * 40, "path": "app.txt", "source": "A-create", "error": "base SHA is stale"},
            "foreign": {"base": "b" * 40, "path": "other.txt", "source": "A-create", "error": "lacks prior-create provenance"},
            "missing": {"base": "b" * 40, "path": "app.txt", "source": None, "error": "source_attempt_ref provenance"},
        }
        for case, values in cases.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); control, _, _ = self.seed_create_candidate_finding(root, source_attempt_ref=values["source"])
                repair = json.loads((root / "repair-contract.json").read_text(encoding="utf-8"))
                packet = self.worker_packet(root, f"A-{case}", mode="repair", base=values["base"], path=values["path"], repair=repair)
                rejected = self.dispatch(control, packet, f"A-{case}", 3, expect=2)
                self.assertIn(values["error"], rejected.stderr)

    def test_repair_return_outside_packet_allowlist_is_still_quarantined(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); control, paths, candidate = self.seed_create_candidate_finding(root)
            repair = json.loads((root / "repair-contract.json").read_text(encoding="utf-8"))
            packet = self.worker_packet(root, "A-repair", mode="repair", base=candidate, repair=repair)
            self.dispatch(control, packet, "A-repair", 3)
            state, _ = ledger.load_state(paths); attempt = ledger.attempt_by_id(state, "A-repair")
            returned = {"identity": {"run_id": "repair-run", "ticket_id": "T-1", "attempt_id": "A-repair", "packet_hash": attempt["packet_hash"], "epoch": 0}, "status": "DONE", "result": "overbroad", "files": [{"path": "other.txt", "operation": "modify"}], "checks": [{"check_id": "oracle", "outcome": "pass", "actual": "fixed", "evidence_ref": "EV-repair"}], "criteria": [{"criterion_id": "C-1", "outcome": "satisfied", "evidence_refs": ["EV-repair"]}]}
            inbox = paths["scratch"] / "A-repair" / "return.json"; write_json(inbox, returned)
            result = run("ingest-return", "--control-root", str(control), "--run-id", "repair-run", "--owner-token", "owner-a", "--revision", "4", "--attempt-id", "A-repair", "--return-file", str(inbox), "--kind", "worker")
            self.assertIn('"quarantined": true', result.stdout)
            final, _ = ledger.load_state(paths)
            self.assertEqual("quarantined", ledger.attempt_by_id(final, "A-repair")["lease"]["state"])

    def test_skill_declares_wait_internal_and_runtime_boundary(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        execute = (ROOT / "phases" / "execute.md").read_text(encoding="utf-8")
        ledger_reference = (ROOT / "references" / "ledger.md").read_text(encoding="utf-8")
        self.assertIn("internal orchestration", skill)
        self.assertIn("Three consecutive waits of at most 60 seconds", skill)
        self.assertIn("do not ask the user", execute)
        self.assertIn("does not own the orchestration turn or runtime wait loop", ledger_reference)


if __name__ == "__main__":
    unittest.main()
