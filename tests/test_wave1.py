import json
import os
import shutil
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


class Wave1Tests(unittest.TestCase):
    def init_run(self, root: Path, run_id: str = "run-1") -> tuple[Path, Path]:
        control = root / "control"
        repo = root / "repo"
        control.mkdir()
        repo.mkdir()
        run("init", "--control-root", str(control), "--repo-root", str(repo), "--run-id", run_id, "--owner-token", "owner-a")
        return control, repo

    def test_corrupt_current_recovers_from_verified_snapshot_and_retains_eight(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            control, _ = self.init_run(Path(directory))
            for _ in range(12):
                state, _ = ledger.load_state(ledger.paths(control, "run-1"))
                run("gate", "--control-root", str(control), "--run-id", "run-1", "--owner-token", "owner-a", "--revision", str(state["revision"]), "--next-action", "checkpoint")
            paths = ledger.paths(control, "run-1")
            snapshots = list((paths["run"] / "snapshots").glob("*.json"))
            self.assertEqual(8, len(snapshots))
            ledger.atomic_write(paths["ledger"], b"{corrupt\n")
            recovered = run("recover", "--control-root", str(control), "--run-id", "run-1", "--owner-token", "owner-a", "--revision", "12")
            self.assertIn("recovered_from", recovered.stdout)
            state, _ = ledger.load_state(paths)
            self.assertEqual("RECOVERING", state["lifecycle"]["control"])
            self.assertTrue((paths["run"] / "snapshots").joinpath("pinned-13-recovery.json").exists())

    def test_effect_journal_is_two_phase_and_pinned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            control, _ = self.init_run(Path(directory))
            prepared = run("prepare-effect", "--control-root", str(control), "--run-id", "run-1", "--owner-token", "owner-a", "--revision", "0", "--operation-id", "OP-1", "--kind", "candidate_commit", "--target", "repo", "--authority-ref", "user-authorized")
            self.assertIn('"state": "prepared"', prepared.stdout)
            receipt = Path(directory) / "receipt.json"
            write_json(receipt, {"operation_id": "OP-1", "target": "repo", "status": "PASS", "result": "commit observed"})
            reconciled = run("reconcile-effect", "--control-root", str(control), "--run-id", "run-1", "--owner-token", "owner-a", "--revision", "1", "--operation-id", "OP-1", "--result", "applied", "--receipt", str(receipt))
            self.assertIn('"state": "applied"', reconciled.stdout)
            state, _ = ledger.load_state(ledger.paths(control, "run-1"))
            self.assertEqual("applied", state["operations"][0]["state"])
            self.assertTrue(any(path.name.startswith("pinned-") for path in (ledger.paths(control, "run-1")["run"] / "snapshots").glob("*.json")))

    def test_cancel_requires_quiesce_stop_and_reconcile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            control, _ = self.init_run(Path(directory))
            run("cancel", "--control-root", str(control), "--run-id", "run-1", "--owner-token", "owner-a", "--revision", "0")
            direct = run("gate", "--control-root", str(control), "--run-id", "run-1", "--owner-token", "owner-a", "--revision", "1", "--control", "CANCELLED", expect=2)
            self.assertIn("direct CANCELLED bypass", direct.stderr)
            evidence = Path(directory) / "stop.json"
            write_json(evidence, {"status": "PASS", "writers_stopped": True, "reconciled": True})
            run("cancel", "--control-root", str(control), "--run-id", "run-1", "--owner-token", "owner-a", "--revision", "1", "--finalize", "--stop-evidence", str(evidence))
            state, _ = ledger.load_state(ledger.paths(control, "run-1"))
            self.assertEqual("CANCELLED", state["lifecycle"]["control"])

    def test_pause_cannot_bypass_quiesce_with_active_attempt_or_prepared_effect(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            control, _ = self.init_run(Path(directory))
            paths = ledger.paths(control, "run-1")
            state, previous = ledger.load_state(paths)
            state["attempts"] = [{
                "id": "A-1", "kind": "worker", "mode": "implement", "subject_ref": "T-1",
                "packet_ref": None, "packet_hash": None, "epoch": 0, "state": "DISPATCHED",
                "lease": {"id": "L-1", "state": "active", "zone": []},
            }]
            state["operations"] = [{"id": "OP-1", "kind": "candidate_commit", "target": "repo", "state": "prepared"}]
            state["revision"] = 1
            state["previous_publication_hash"] = ledger.sha256_bytes(previous)
            ledger.validate_ledger(state)
            ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))

            direct = run("gate", "--control-root", str(control), "--run-id", "run-1", "--owner-token", "owner-a", "--revision", "1", "--control", "PAUSED", expect=2)

            self.assertIn("prior QUIESCING", direct.stderr)
            quiesce = run("gate", "--control-root", str(control), "--run-id", "run-1", "--owner-token", "owner-a", "--revision", "1", "--control", "QUIESCING")
            blocked = run("gate", "--control-root", str(control), "--run-id", "run-1", "--owner-token", "owner-a", "--revision", "2", "--control", "PAUSED", expect=2)
            self.assertIn("stopped writers", blocked.stderr)
            final, _ = ledger.load_state(paths)
            self.assertEqual("QUIESCING", final["lifecycle"]["control"])
            self.assertEqual(2, final["revision"])
            self.assertIn('"control": "QUIESCING"', quiesce.stdout)

    def test_audit_includes_ignored_and_rejects_escape_and_mode_type_risks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            root.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / ".gitignore").write_text("ignored.out\n", encoding="utf-8")
            (root / "tracked.txt").write_text("BASE\n", encoding="utf-8")
            subprocess.run(["git", "add", ".gitignore", "tracked.txt"], cwd=root, check=True)
            subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "base"], cwd=root, check=True)
            (root / "ignored.out").write_text("IGNORED\n", encoding="utf-8")
            (root / "escape").symlink_to("/tmp")
            baseline = Path(directory) / "baseline.json"
            declared = Path(directory) / "declared.json"
            zone = Path(directory) / "zone.json"
            write_json(baseline, {"files": []})
            write_json(declared, [{"path": "tracked.txt"}])
            write_json(zone, [{"path": "tracked.txt", "operations": ["modify"]}])
            result = run("audit-write-set", "--root", str(root), "--baseline", str(baseline), "--declared", str(declared), "--zone", str(zone))
            payload = json.loads(result.stdout)
            self.assertIn("ignored.out", payload["actual_paths"])
            self.assertIn("escape", {item["path"] for item in payload["unsafe_paths"]})
            self.assertFalse(payload["pass"])

    def test_nested_contracts_reject_empty_worker_and_review_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker = root / "worker.json"
            write_json(worker, {"identity": {"run_id": "r", "attempt_id": "a", "packet_hash": "0" * 64, "epoch": 0}, "status": "DONE", "result": "ok", "files": [], "checks": [], "criteria": []})
            run("validate", "--file", str(worker), "--kind", "worker_return", expect=2)
            review = root / "review.json"
            write_json(review, {"identity": {"run_id": "r", "attempt_id": "a", "packet_hash": "0" * 64, "epoch": 0}, "subject_fingerprint": "candidate", "verdict": "PASS", "coverage": [], "checks": [], "context_refs": [], "findings": []})
            run("validate", "--file", str(review), "--kind", "review_return", expect=2)

    def test_worker_done_candidate_review_authority_and_idempotent_lease_closure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            control, repo = self.init_run(Path(directory))
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            (repo / "app.txt").write_text("BASE\n", encoding="utf-8")
            subprocess.run(["git", "add", "app.txt"], cwd=repo, check=True)
            subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "base"], cwd=repo, check=True)
            base_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=True).stdout.strip()
            paths = ledger.paths(control, "run-1")
            state, previous = ledger.load_state(paths)
            intent = paths["docs"] / "intent" / "v1.md"
            ledger.atomic_write(intent, b"# intent\n")
            state.update({
                "revision": 1,
                "previous_publication_hash": ledger.sha256_bytes(previous),
                "repository": {**state["repository"], "branch": "main", "initial_head": base_sha, "checkout": str(repo)},
                "documents": [{"id": "doc-1", "version": "v1", "path": str(intent), "hash": ledger.sha256_file(intent), "kind": "intent", "section_anchors": []}],
                "intent": {"current_revision": "intent-v1", "document_ref": "doc-1", "approved_amendments": []},
                "requirements": [{"id": "R-1", "version": "v1", "status": "active", "provenance_refs": ["doc-1"], "criterion_refs": ["C-1"]}],
                "criteria": [{"id": "C-1", "version": "v1", "requirement_refs": ["R-1"], "oracle": "app", "status": "active"}],
                "contracts": [{"id": "contract-1", "version": "v1", "status": "active", "provenance_refs": ["doc-1"]}],
                "tickets": [{"id": "T-1", "goal_ref": "G-1", "criterion_refs": ["C-1"], "contract_refs": ["contract-1"], "dependency_refs": [], "state": "READY", "complexity": "bounded", "risk": "routine", "zone": [{"path": "app.txt", "operations": ["modify"]}], "current_attempt": None, "replacement_refs": []}],
                "lifecycle": {"phase": "EXECUTE", "control": "ACTIVE", "next_action": {"kind": "dispatch", "subject_refs": [], "preconditions": [], "read_refs": []}},
            })
            ledger.validate_ledger(state)
            ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
            packet = Path(directory) / "worker.json"
            write_json(packet, {"identity": {"run_id": "run-1", "ticket_id": "T-1", "attempt_id": "A-1", "epoch": 0}, "kind": "worker", "mode": "implement", "goal": "update app", "acceptance": [{"criterion_id": "C-1"}], "workspace": {"root": str(repo), "expected_base": base_sha}, "write": {"allow": [{"path": "app.txt", "operations": ["modify"]}]}, "verification": [{"check_id": "oracle", "required": True}], "risk": {"level": "routine"}, "context": [{"ref": "contracts/worker.md"}], "return_target": {"transport": "file", "path": "return.json"}})
            route = Path(directory) / "route.json"
            write_json(route, {"id": "route-1", "capability": "worker", "reasoning": "bounded", "adequacy": "CONFIRMED", "context_grade": "PACKET_SCOPED"})
            run("dispatch", "--control-root", str(control), "--run-id", "run-1", "--owner-token", "owner-a", "--revision", "1", "--ticket-id", "T-1", "--attempt-id", "A-1", "--lease-id", "L-1", "--route-id", "route-1", "--packet", str(packet), "--route", str(route))
            state, _ = ledger.load_state(paths)
            worker_return = paths["scratch"] / "A-1" / "return.json"
            write_json(worker_return, {"identity": {"run_id": "run-1", "ticket_id": "T-1", "attempt_id": "A-1", "packet_hash": state["attempts"][0]["packet_hash"], "epoch": 0}, "status": "DONE", "result": "updated", "files": [{"path": "app.txt", "operation": "modify"}], "checks": [{"check_id": "oracle", "outcome": "pass", "actual": "VALUE=42", "evidence_ref": "ev-worker"}], "criteria": [{"criterion_id": "C-1", "outcome": "satisfied", "evidence_refs": ["ev-worker"]}]})
            run("ingest-return", "--control-root", str(control), "--run-id", "run-1", "--owner-token", "owner-a", "--revision", "2", "--attempt-id", "A-1", "--return-file", str(worker_return), "--kind", "worker")
            run("prepare-effect", "--control-root", str(control), "--run-id", "run-1", "--owner-token", "owner-a", "--revision", "3", "--operation-id", "OP-1", "--kind", "candidate_commit", "--target", str(repo), "--expected-before", base_sha, "--authority-ref", "test")
            (repo / "app.txt").write_text("VALUE=42\n", encoding="utf-8")
            subprocess.run(["git", "add", "app.txt"], cwd=repo, check=True)
            subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "candidate"], cwd=repo, check=True)
            candidate_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=True).stdout.strip()
            tree_sha = subprocess.run(["git", "rev-parse", "HEAD^{tree}"], cwd=repo, text=True, capture_output=True, check=True).stdout.strip()
            receipt = Path(directory) / "commit.json"
            write_json(receipt, {"status": "PASS", "checkout": str(repo), "base_sha": base_sha, "commit_sha": candidate_sha, "tree_sha": tree_sha, "authority_ref": "test", "receipt_ref": "receipt"})
            run("candidate", "--control-root", str(control), "--run-id", "run-1", "--owner-token", "owner-a", "--revision", "4", "--attempt-id", "A-1", "--commit-receipt", str(receipt), "--operation-id", "OP-1")
            state, _ = ledger.load_state(paths)
            self.assertEqual("CANDIDATE", state["tickets"][0]["state"])
            review_packet = Path(directory) / "review.json"
            write_json(review_packet, {"identity": {"run_id": "run-1", "attempt_id": "A-review-1", "epoch": 0}, "kind": "review", "mandate": "routine change review", "subject_fingerprint": candidate_sha, "criteria": [{"criterion_id": "C-1"}], "axes": ["correctness"], "return_target": {"transport": "file", "path": "review.json"}})
            run("prepare-review", "--control-root", str(control), "--run-id", "run-1", "--owner-token", "owner-a", "--revision", "5", "--ticket-id", "T-1", "--review-attempt-id", "A-review-1", "--lease-id", "RL-1", "--packet", str(review_packet))
            state, raw = ledger.load_state(paths)
            review_attempt = next(item for item in state["attempts"] if item["id"] == "A-review-1")
            review_return = paths["scratch"] / "A-review-1" / "review-return.json"
            write_json(review_return, {"identity": {"run_id": "run-1", "attempt_id": "A-review-1", "packet_hash": review_attempt["packet_hash"], "epoch": 0}, "subject_fingerprint": candidate_sha, "verdict": "PASS", "coverage": [{"criterion_id": "C-1", "outcome": "fulfilled", "evidence_refs": ["ev-review"]}], "checks": [{"check_id": "correctness", "axis": "correctness", "outcome": "fulfilled", "actual": "VALUE=42", "evidence_ref": "ev-review"}], "context_refs": ["clean-review-context"], "findings": []})
            integrity = Path(directory) / "integrity.json"
            write_json(integrity, {"status": "PASS", "candidate_fingerprint": candidate_sha, "ledger_hash": ledger.sha256_bytes(raw)})
            run("integrate", "--control-root", str(control), "--run-id", "run-1", "--owner-token", "owner-a", "--revision", "6", "--attempt-id", "A-review-1", "--review-file", str(review_return), "--integrity-receipt", str(integrity), "--review-id", "REV-1")
            final, _ = ledger.load_state(paths)
            self.assertEqual("INTEGRATED", final["tickets"][0]["state"])
            self.assertEqual("review", next(item for item in final["attempts"] if item["id"] == "A-review-1")["kind"])
            self.assertEqual("released", next(item for item in final["attempts"] if item["id"] == "A-1")["lease"]["state"])
            self.assertEqual("released", next(item for item in final["attempts"] if item["id"] == "A-review-1")["lease"]["state"])
            repeated = run("integrate", "--control-root", str(control), "--run-id", "run-1", "--owner-token", "owner-a", "--revision", str(final["revision"]), "--attempt-id", "A-review-1", "--review-file", str(review_return), "--integrity-receipt", str(integrity), "--review-id", "REV-1")
            self.assertIn('"idempotent": true', repeated.stdout)
            repeated_state, _ = ledger.load_state(paths)
            self.assertEqual(final["revision"], repeated_state["revision"])
            self.assertEqual("released", next(item for item in repeated_state["attempts"] if item["id"] == "A-1")["lease"]["state"])

    def test_frozen_e03m_manual_files_still_validate(self) -> None:
        fixture = ROOT / "experiments" / "fixtures" / "e03m" / "seed-repo" / ".autopilot" / "scratch" / "e03m-manual-g5-2026-09-13" / "A-E03M-WORKER-1"
        run("validate", "--file", str(fixture / "acceptance-return.json"), "--kind", "acceptance_return")
        run("validate", "--file", str(fixture / "environment-receipt.json"), "--kind", "environment_receipt")
        run("validate", "--file", str(fixture / "context-receipt.json"), "--kind", "context_receipt")
        packet = ROOT / "experiments" / "fixtures" / "e03m" / "g5-bundle" / "packet.json"
        run("validate", "--file", str(packet), "--kind", "acceptance_packet")

    def test_e03m_manual_import_roundtrip_remains_resumable(self) -> None:
        source = ROOT / "experiments" / "fixtures" / "e03m" / "seed-repo"
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory) / "seed-repo"
            shutil.copytree(source, copied, symlinks=True)
            paths = ledger.paths(copied, "e03m-manual-g5-2026-09-13")
            state, raw = ledger.load_state(paths)
            inbox = paths["scratch"] / "A-E03M-WORKER-1"
            integrity = Path(directory) / "post-import-integrity.json"
            write_json(integrity, {"status": "PASS", "candidate_fingerprint": state["attempts"][0]["candidate_sha"], "ledger_hash": ledger.sha256_bytes(raw)})
            result = run("import-manual", "--control-root", str(copied), "--run-id", "e03m-manual-g5-2026-09-13", "--owner-token", state["owner"]["token"], "--revision", str(state["revision"]), "--attempt-id", "A-E03M-WORKER-1", "--return-file", str(inbox / "acceptance-return.json"), "--environment-receipt", str(inbox / "environment-receipt.json"), "--context-receipt", str(inbox / "context-receipt.json"), "--integrity-receipt", str(integrity), "--intent-revision", "intent-v1", "--candidate-fingerprint", state["attempts"][0]["candidate_sha"], "--required-criteria", "C-E03M-1")
            self.assertIn('"imported": true', result.stdout)
            final, _ = ledger.load_state(paths)
            self.assertEqual("INTEGRATED", final["tickets"][0]["state"])
            self.assertEqual("released", final["attempts"][0]["lease"]["state"])


if __name__ == "__main__":
    unittest.main()
