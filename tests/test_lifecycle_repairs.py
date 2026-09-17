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

    def seed_completed_repair_chain(self, root: Path, completed_repairs: int) -> tuple[Path, dict[str, Path], str, dict[str, object]]:
        control, repo, paths = self.init_ticket(root, operation="create")
        candidates = [char * 40 for char in "bcdefghijklmnop"]
        if completed_repairs >= len(candidates) - 1:
            raise AssertionError("test repair chain is too long")

        def worker_return(attempt_id: str, packet_hash: str, operation: str) -> str:
            payload = {
                "identity": {"run_id": "repair-run", "ticket_id": "T-1", "attempt_id": attempt_id, "packet_hash": packet_hash, "epoch": 0},
                "status": "DONE", "result": f"{operation}d app.txt", "files": [{"path": "app.txt", "operation": operation}],
                "checks": [{"check_id": "oracle", "outcome": "pass", "actual": "ok", "evidence_ref": f"EV-{attempt_id}"}],
                "criteria": [{"criterion_id": "C-1", "outcome": "satisfied", "evidence_refs": [f"EV-{attempt_id}"]}],
            }
            return ledger.object_store(paths, ledger.canonical_bytes(payload))

        state, previous = ledger.load_state(paths)
        attempts: list[dict[str, object]] = []
        findings: list[dict[str, object]] = []
        decisions: list[dict[str, object]] = []
        create_hash = "1" * 64
        create_return = worker_return("A-create", create_hash, "create")
        attempts.append({
            "id": "A-create", "kind": "worker", "mode": "implement", "subject_ref": "T-1",
            "packet_ref": "objects/" + "2" * 64, "packet_hash": create_hash, "epoch": 0, "state": "RETURNED",
            "lease": {"id": "L-create", "state": "released", "zone": [{"path": "app.txt", "operations": ["create"]}]},
            "route_ref": "route-create", "checkout": str(repo), "base_sha": "a" * 40,
            "candidate_sha": candidates[0], "candidate_tree_sha": "1" * 40,
            "return_ref": f"objects/{create_return}", "finding_refs": [],
        })
        prior_worker = "A-create"
        prior_candidate = candidates[0]
        for index in range(1, completed_repairs + 2):
            finding_id = f"F-{index}"
            review_id = f"R-{index}"
            attempts.append({
                "id": review_id, "kind": "review", "mode": "change", "subject_ref": "T-1",
                "packet_ref": "objects/" + str((index + 2) % 10) * 64, "packet_hash": str((index + 3) % 10) * 64,
                "epoch": 0, "state": "RETURNED", "lease": {"id": f"L-{review_id}", "state": "released", "zone": []},
                "route_ref": None, "checkout": None, "base_sha": prior_candidate, "candidate_sha": prior_candidate,
                "candidate_tree_sha": str((index + 1) % 10) * 40, "return_ref": "objects/" + str((index + 4) % 10) * 64,
                "finding_refs": [finding_id], "subject_fingerprint": prior_candidate, "review_result": "BLOCK",
            })
            findings.append({
                "id": finding_id, "axis": "correctness", "impact": "blocking", "claim": f"repair finding {index}",
                "expected": "correct", "actual": "incorrect", "evidence": f"EV-{review_id}",
                "affected_refs": ["T-1"], "source_ref": review_id, "intent_revision": None,
                "repair_contract_ref": None, "invalidated_by": [],
            })
            if index > completed_repairs:
                break
            repair = {
                "cause": "implementation", "finding_ref": finding_id, "hypothesis": f"root cause {index}",
                "expected_proof": f"proof {index}", "stopping_condition": f"stop {index}",
                "causal_change": f"change {index}", "source_attempt_ref": review_id,
            }
            contract_digest = ledger.object_store(paths, ledger.canonical_bytes(repair))
            authorization_id = f"AUTH-{index}"
            decisions.append({
                "id": authorization_id, "type": "repair_authorization", "status": "authorized", "decision": "REPAIR",
                "reason": repair["hypothesis"], "evidence_refs": [finding_id, f"objects/{contract_digest}"],
                "affected_refs": ["T-1", finding_id], "intent_revision": None, "invalidated_by": [],
            })
            findings[-1]["repair_contract_ref"] = authorization_id
            attempt_id = f"A-repair-{index}"
            packet_hash = str((index + 5) % 10) * 64
            return_digest = worker_return(attempt_id, packet_hash, "modify")
            candidate = candidates[index]
            attempts.append({
                "id": attempt_id, "kind": "worker", "mode": "repair", "subject_ref": "T-1",
                "packet_ref": "objects/" + str((index + 6) % 10) * 64, "packet_hash": packet_hash,
                "epoch": 0, "state": "RETURNED", "lease": {"id": f"L-{attempt_id}", "state": "released", "zone": [{"path": "app.txt", "operations": ["modify"]}]},
                "route_ref": f"route-{attempt_id}", "checkout": str(repo), "base_sha": prior_candidate,
                "candidate_sha": candidate, "candidate_tree_sha": str((index + 2) % 10) * 40,
                "return_ref": f"objects/{return_digest}", "finding_refs": [], "repair_contract": repair,
                "repair_authorization_ref": authorization_id, "failure_signature": ledger.repair_signature(repair),
                "repair_lease_provenance": {
                    "authorization_ref": authorization_id, "finding_ref": finding_id,
                    "source_attempt_ref": prior_worker, "candidate_sha": prior_candidate,
                    "packet_base_sha": prior_candidate,
                    "expanded_entries": [{"path": "app.txt", "operations": ["modify"]}],
                },
            })
            prior_worker = attempt_id
            prior_candidate = candidate

        state["attempts"] = attempts
        state["findings"] = findings
        state["decisions"] = decisions
        state["tickets"][0]["state"] = "REVIEW"
        state["tickets"][0]["current_attempt"] = prior_worker
        state["lifecycle"]["control"] = "BLOCKED"
        state["lifecycle"]["reason"] = "review_not_pass"
        state["revision"] = 2
        state["previous_publication_hash"] = ledger.sha256_bytes(previous)
        ledger.validate_ledger(state)
        ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
        next_index = completed_repairs + 1
        next_repair = {
            "cause": "implementation", "finding_ref": f"F-{next_index}", "hypothesis": f"root cause {next_index}",
            "expected_proof": f"proof {next_index}", "stopping_condition": f"stop {next_index}",
            "causal_change": f"change {next_index}", "source_attempt_ref": f"R-{next_index}",
        }
        repair_path = root / "repair-contract.json"
        write_json(repair_path, next_repair)
        run(
            "authorize-repair", "--control-root", str(control), "--run-id", "repair-run", "--owner-token", "owner-a",
            "--revision", "2", "--ticket-id", "T-1", "--finding-ref", f"F-{next_index}",
            "--authorization-id", f"AUTH-{next_index}", "--repair-contract", str(repair_path),
        )
        return control, paths, prior_candidate, next_repair

    def seed_legacy_quarantined_repair(self, root: Path, *, foreign_change: bool = False, issue_type: str = "write_set_violation") -> tuple[Path, Path, dict[str, Path], Path, str]:
        control, repo, paths = self.init_ticket(root, operation="create")
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        (repo / "README.md").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "base"], cwd=repo, check=True)
        (repo / "app.txt").write_text("created\n", encoding="utf-8")
        subprocess.run(["git", "add", "app.txt"], cwd=repo, check=True)
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "create candidate"], cwd=repo, check=True)
        candidate = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=True).stdout.strip()

        baseline_files = []
        for name in ("README.md", "app.txt"):
            path = repo / name
            baseline_files.append({"path": name, "type": "file", "mode": path.stat().st_mode & 0o777, "sha256": ledger.sha256_file(path)})
        baseline = root / "repair-baseline.json"
        write_json(baseline, {"base_sha": candidate, "files": baseline_files})
        (repo / "app.txt").write_text("repaired\n", encoding="utf-8")
        if foreign_change:
            (repo / "README.md").write_text("foreign\n", encoding="utf-8")

        prior_return = {
            "identity": {"run_id": "repair-run", "ticket_id": "T-1", "attempt_id": "A-create", "packet_hash": "1" * 64, "epoch": 0},
            "status": "DONE", "result": "created app.txt", "files": [{"path": "app.txt", "operation": "create"}],
            "checks": [{"check_id": "oracle", "outcome": "pass", "actual": "created", "evidence_ref": "EV-create"}],
            "criteria": [{"criterion_id": "C-1", "outcome": "satisfied", "evidence_refs": ["EV-create"]}],
        }
        current_return = {
            "identity": {"run_id": "repair-run", "ticket_id": "T-1", "attempt_id": "A-repair", "packet_hash": None, "epoch": 0},
            "status": "DONE", "result": "repaired app.txt", "files": [{"path": "app.txt", "operation": "modify"}],
            "checks": [{"check_id": "oracle", "outcome": "pass", "actual": "repaired", "evidence_ref": "EV-repair"}],
            "criteria": [{"criterion_id": "C-1", "outcome": "satisfied", "evidence_refs": ["EV-repair"]}],
        }
        repair = {"cause": "implementation", "finding_ref": "F-1", "hypothesis": "created content is wrong", "expected_proof": "regression observes corrected content", "stopping_condition": "stop after the focused regression passes", "causal_change": "replace the generated value", "source_attempt_ref": "A-review"}
        packet = {
            "identity": {"run_id": "repair-run", "ticket_id": "T-1", "attempt_id": "A-repair", "epoch": 0},
            "kind": "worker", "mode": "repair", "goal": "repair created file", "acceptance": [{"criterion_id": "C-1"}],
            "workspace": {"root": str(repo), "expected_base": candidate},
            "write": {"allow": [{"path": "app.txt", "operations": ["modify"]}]},
            "verification": [{"check_id": "oracle", "required": True}], "risk": {"level": "routine"},
            "context": [{"ref": "contracts/worker.md"}], "return_target": {"path": "return.json"}, "repair": repair,
        }
        packet_digest = ledger.object_store(paths, ledger.canonical_bytes(packet))
        current_return["identity"]["packet_hash"] = packet_digest
        prior_digest = ledger.object_store(paths, ledger.canonical_bytes(prior_return))
        current_digest = ledger.object_store(paths, ledger.canonical_bytes(current_return))
        state, previous = ledger.load_state(paths)
        state["attempts"] = [
            {"id": "A-create", "kind": "worker", "mode": "implement", "subject_ref": "T-1", "packet_ref": "objects/" + "2" * 64, "packet_hash": "1" * 64, "epoch": 0, "state": "RETURNED", "lease": {"id": "L-create", "state": "released", "zone": [{"path": "app.txt", "operations": ["create"]}]}, "route_ref": "route-create", "checkout": str(repo), "base_sha": "a" * 40, "candidate_sha": candidate, "candidate_tree_sha": subprocess.run(["git", "rev-parse", "HEAD^{tree}"], cwd=repo, text=True, capture_output=True, check=True).stdout.strip(), "return_ref": f"objects/{prior_digest}", "finding_refs": []},
            {"id": "A-review", "kind": "review", "mode": "change", "subject_ref": "T-1", "packet_ref": "objects/" + "3" * 64, "packet_hash": "4" * 64, "epoch": 0, "state": "RETURNED", "lease": {"id": "L-review", "state": "released", "zone": []}, "base_sha": candidate, "candidate_sha": candidate, "candidate_tree_sha": None, "return_ref": "objects/" + "5" * 64, "finding_refs": ["F-1"], "subject_fingerprint": candidate, "review_result": "BLOCK"},
            {"id": "A-repair", "kind": "worker", "mode": "repair", "subject_ref": "T-1", "packet_ref": f"objects/{packet_digest}", "packet_hash": packet_digest, "epoch": 0, "state": "RETURNED", "lease": {"id": "L-repair", "state": "quarantined", "zone": [{"path": "app.txt", "operations": ["create"]}]}, "route_ref": "route-repair", "checkout": str(repo), "base_sha": candidate, "candidate_sha": None, "candidate_tree_sha": None, "return_ref": f"objects/{current_digest}", "finding_refs": ["ISS-quarantine"], "repair_contract": repair, "failure_signature": ledger.repair_signature(repair)},
        ]
        state["findings"] = [{"id": "F-1", "axis": "correctness", "impact": "blocking", "claim": "created file needs correction", "expected": "correct", "actual": "incorrect", "evidence": "EV-review", "affected_refs": ["A-review"], "source_ref": "A-review", "intent_revision": None, "repair_contract_ref": "AUTH-1", "invalidated_by": []}]
        state["decisions"] = [{"id": "AUTH-1", "type": "repair_authorization", "status": "authorized", "decision": "REPAIR", "reason": repair["hypothesis"], "evidence_refs": ["F-1"], "affected_refs": ["T-1", "F-1"], "intent_revision": None, "invalidated_by": []}]
        state["issues"] = [{"id": "ISS-quarantine", "type": issue_type, "cause": "ownership", "impact": "blocking", "affected_refs": ["T-1", "A-repair"], "expected": "lease match", "actual": '[{"operation":"modify","path":"app.txt"}]', "disposition": "quarantine", "resolution_condition": "audited reconciliation", "owner": None, "failure_signature": None, "finding_ref": None, "source_ref": "A-repair", "intent_revision": None, "decision_ref": None, "invalidated_by": []}]
        state["tickets"][0]["state"] = "BLOCKED"
        state["tickets"][0]["current_attempt"] = "A-repair"
        state["lifecycle"] = {"phase": "EXECUTE", "control": "BLOCKED", "reason": "worker_done", "issue_refs": ["ISS-quarantine"], "stop_target": None, "next_action": {"kind": "triage_or_repair", "subject_refs": ["A-repair"], "preconditions": [], "read_refs": []}}
        state["revision"] = 2
        state["previous_publication_hash"] = ledger.sha256_bytes(previous)
        ledger.validate_ledger(state)
        ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
        return control, repo, paths, baseline, candidate

    def reconcile_legacy(self, control: Path, baseline: Path | None, candidate: str, *, expect: int = 0, base: str | None = None) -> subprocess.CompletedProcess[str]:
        args = ["reconcile-quarantined-attempt", "--control-root", str(control), "--run-id", "repair-run", "--owner-token", "owner-a", "--revision", "2", "--ticket-id", "T-1", "--attempt-id", "A-repair", "--prior-attempt-id", "A-create", "--finding-ref", "F-1", "--candidate-sha", candidate, "--base-sha", base or candidate, "--reconciliation-id", "QR-1", "--actor", "test-operator"]
        if baseline is not None:
            args.extend(["--baseline", str(baseline)])
        return run(*args, expect=expect)

    def seed_blocked_no_write_repair(self, root: Path) -> tuple[Path, Path, dict[str, Path], str, str]:
        control, repo, paths = self.init_ticket(root)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        (repo / "README.md").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "base"], cwd=repo, check=True)
        old_candidate = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=True).stdout.strip()
        (repo / "app.txt").write_text("candidate\n", encoding="utf-8")
        subprocess.run(["git", "add", "app.txt"], cwd=repo, check=True)
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "candidate"], cwd=repo, check=True)
        candidate = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=True).stdout.strip()
        candidate_tree = subprocess.run(["git", "rev-parse", "HEAD^{tree}"], cwd=repo, text=True, capture_output=True, check=True).stdout.strip()

        def worker_return(attempt_id: str, packet_hash: str, status: str, files: list[dict[str, str]]) -> str:
            payload = {
                "identity": {"run_id": "repair-run", "ticket_id": "T-1", "attempt_id": attempt_id, "packet_hash": packet_hash, "epoch": 0},
                "status": status, "result": "candidate complete" if status == "DONE" else "blocked before first write",
                "files": files,
                "checks": [{"check_id": "oracle", "outcome": "pass" if status == "DONE" else "not_run", "actual": "clean", "evidence_ref": f"EV-{attempt_id}"}],
                "criteria": [{"criterion_id": "C-1", "outcome": "satisfied" if status == "DONE" else "unverifiable", "evidence_refs": [f"EV-{attempt_id}"]}],
                **({"issues": [{"id": "ISS-blocked", "type": "scope_blocker", "cause": "ownership", "impact": "blocking", "affected_refs": ["T-1"], "disposition": "authorize changed scope"}]} if status == "BLOCKED" else {}),
            }
            return ledger.object_store(paths, ledger.canonical_bytes(payload))

        old_hash, current_hash, blocked_hash = "1" * 64, "2" * 64, "3" * 64
        old_return = worker_return("A-old", old_hash, "DONE", [{"path": "README.md", "operation": "modify"}])
        current_return = worker_return("A-current", current_hash, "DONE", [{"path": "app.txt", "operation": "modify"}])
        blocked_return = worker_return("A-blocked", blocked_hash, "BLOCKED", [])
        state, previous = ledger.load_state(paths)
        state["attempts"] = [
            {"id": "A-old", "kind": "worker", "mode": "implement", "subject_ref": "T-1", "packet_ref": "objects/" + "4" * 64, "packet_hash": old_hash, "epoch": 0, "state": "RETURNED", "lease": {"id": "L-old", "state": "released", "zone": [{"path": "README.md", "operations": ["modify"]}]}, "route_ref": "route-old", "checkout": str(repo), "base_sha": None, "candidate_sha": old_candidate, "candidate_tree_sha": subprocess.run(["git", "rev-parse", f"{old_candidate}^{{tree}}"], cwd=repo, text=True, capture_output=True, check=True).stdout.strip(), "return_ref": f"objects/{old_return}", "finding_refs": []},
            {"id": "A-current", "kind": "worker", "mode": "repair", "subject_ref": "T-1", "packet_ref": "objects/" + "5" * 64, "packet_hash": current_hash, "epoch": 0, "state": "RETURNED", "lease": {"id": "L-current", "state": "released", "zone": [{"path": "app.txt", "operations": ["modify"]}]}, "route_ref": "route-current", "checkout": str(repo), "base_sha": old_candidate, "candidate_sha": candidate, "candidate_tree_sha": candidate_tree, "return_ref": f"objects/{current_return}", "finding_refs": []},
            {"id": "A-blocked", "kind": "worker", "mode": "repair", "subject_ref": "T-1", "packet_ref": "objects/" + "6" * 64, "packet_hash": blocked_hash, "epoch": 0, "state": "RETURNED", "lease": {"id": "L-blocked", "state": "active", "zone": [{"path": "app.txt", "operations": ["modify"]}]}, "route_ref": "route-blocked", "checkout": str(repo), "base_sha": candidate, "candidate_sha": None, "candidate_tree_sha": None, "return_ref": f"objects/{blocked_return}", "finding_refs": ["ISS-blocked"], "repair_contract": {"cause": "implementation", "finding_ref": "F-old", "hypothesis": "old", "expected_proof": "old proof", "stopping_condition": "old stop", "causal_change": "old change", "source_attempt_ref": "A-current"}, "failure_signature": "f" * 64, "repair_lease_provenance": {"authorization_ref": "AUTH-old", "finding_ref": "F-old", "source_attempt_ref": "A-current", "candidate_sha": candidate, "packet_base_sha": candidate, "expanded_entries": [{"path": "app.txt", "operations": ["modify"]}] }},
        ]
        state["issues"] = [{"id": "ISS-blocked", "type": "scope_blocker", "cause": "ownership", "impact": "blocking", "affected_refs": ["T-1", "A-blocked"], "expected": "bounded repair", "actual": "scope too narrow", "disposition": "authorize changed scope", "resolution_condition": "fresh authorization", "owner": None, "failure_signature": None, "finding_ref": None, "source_ref": "A-blocked", "intent_revision": None, "invalidated_by": []}]
        state["tickets"][0]["state"] = "BLOCKED"
        state["tickets"][0]["current_attempt"] = "A-blocked"
        state["lifecycle"] = {"phase": "EXECUTE", "control": "BLOCKED", "reason": "worker_blocked", "issue_refs": ["ISS-blocked"], "stop_target": None, "next_action": {"kind": "triage_or_repair", "subject_refs": ["A-blocked"], "preconditions": [], "read_refs": []}}
        state["revision"] = 2
        state["previous_publication_hash"] = ledger.sha256_bytes(previous)
        ledger.validate_ledger(state)
        ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
        return control, repo, paths, old_candidate, candidate

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

    def test_close_blocked_no_write_repair_restores_last_candidate_and_allows_new_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, _, paths, _, candidate = self.seed_blocked_no_write_repair(root)
            before, _ = ledger.load_state(paths)
            before_attempt_ids = [item["id"] for item in before["attempts"]]
            result = json.loads(run("close-blocked-attempt", "--control-root", str(control), "--run-id", "repair-run", "--owner-token", "owner-a", "--revision", "2", "--ticket-id", "T-1", "--attempt-id", "A-blocked").stdout)
            self.assertFalse(result["idempotent"])
            self.assertEqual("A-current", result["restored_attempt_id"])
            self.assertEqual(candidate, result["candidate_sha"])
            state, _ = ledger.load_state(paths)
            self.assertEqual(before_attempt_ids, [item["id"] for item in state["attempts"]])
            self.assertEqual("released", ledger.attempt_by_id(state, "A-blocked")["lease"]["state"])
            self.assertIsNone(ledger.attempt_by_id(state, "A-blocked")["candidate_sha"])
            self.assertEqual("A-current", state["tickets"][0]["current_attempt"])
            self.assertEqual("BLOCKED", state["tickets"][0]["state"])
            self.assertEqual("authorize_repair", state["lifecycle"]["next_action"]["kind"])
            receipt = ledger.stored_payload(paths, ledger.attempt_by_id(state, "A-blocked")["blocked_closure_ref"], "test closure receipt")
            self.assertTrue(receipt["write_set_audit"]["pass"])
            self.assertEqual([], receipt["write_set_audit"]["changed_paths"])
            self.assertEqual("A-current", receipt["restored_attempt_ref"])
            self.assertTrue(any(item["type"] == "blocked_attempt_closure" for item in state["decisions"]))

            repeated = json.loads(run("restore-last-validated-candidate", "--control-root", str(control), "--run-id", "repair-run", "--owner-token", "owner-a", "--revision", "2", "--ticket-id", "T-1", "--attempt-id", "A-blocked").stdout)
            self.assertTrue(repeated["idempotent"])
            self.assertEqual(state["revision"], ledger.load_state(paths)[0]["revision"])

            repair = {"cause": "ownership", "finding_ref": "ISS-blocked", "hypothesis": "scope omitted one required fixture", "expected_proof": "changed packet covers the fixture", "stopping_condition": "focused regression and suite pass", "causal_change": "expand the replacement packet", "source_attempt_ref": "A-current"}
            repair_path = root / "replacement-repair.json"; write_json(repair_path, repair)
            run("authorize-repair", "--control-root", str(control), "--run-id", "repair-run", "--owner-token", "owner-a", "--revision", "3", "--ticket-id", "T-1", "--finding-ref", "ISS-blocked", "--authorization-id", "AUTH-replacement", "--repair-contract", str(repair_path))
            packet = self.worker_packet(root, "A-replacement", mode="repair", base=candidate, repair=repair)
            self.dispatch(control, packet, "A-replacement", 4)
            cycled, _ = ledger.load_state(paths)
            self.assertEqual("A-replacement", cycled["tickets"][0]["current_attempt"])
            self.assertEqual("RUNNING", cycled["tickets"][0]["state"])

    def test_close_blocked_attempt_rejects_nonblocked_candidate_dirty_and_stale_cases(self) -> None:
        mutations = {
            "nonblocked-return": (lambda state, repo, paths, old, candidate: self._replace_blocked_return(state, paths, status="FAILED", files=[]), "exact validated BLOCKED return"),
            "declared-files": (lambda state, repo, paths, old, candidate: self._replace_blocked_return(state, paths, status="BLOCKED", files=[{"path": "app.txt", "operation": "modify"}]), "exact validated BLOCKED return declaring no files"),
            "candidate-present": (lambda state, repo, paths, old, candidate: ledger.attempt_by_id(state, "A-blocked").update({"candidate_sha": candidate}), "candidate_sha and candidate_tree_sha to be null"),
            "stale-base": (lambda state, repo, paths, old, candidate: ledger.attempt_by_id(state, "A-blocked").update({"base_sha": old}), "last validated same-ticket candidate"),
            "released-lease": (lambda state, repo, paths, old, candidate: ledger.attempt_by_id(state, "A-blocked")["lease"].update({"state": "released"}), "active lease"),
        }
        for name, (mutate, expected) in mutations.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); control, repo, paths, old, candidate = self.seed_blocked_no_write_repair(root)
                state, _ = ledger.load_state(paths); mutate(state, repo, paths, old, candidate); ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
                rejected = run("close-blocked-attempt", "--control-root", str(control), "--run-id", "repair-run", "--owner-token", "owner-a", "--revision", "2", "--ticket-id", "T-1", "--attempt-id", "A-blocked", expect=2)
                self.assertIn(expected, rejected.stderr)
                unchanged, _ = ledger.load_state(paths)
                self.assertEqual("A-blocked", unchanged["tickets"][0]["current_attempt"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); control, repo, paths, _, _ = self.seed_blocked_no_write_repair(root)
            (repo / "app.txt").write_text("dirty\n", encoding="utf-8")
            rejected = run("close-blocked-attempt", "--control-root", str(control), "--run-id", "repair-run", "--owner-token", "owner-a", "--revision", "2", "--ticket-id", "T-1", "--attempt-id", "A-blocked", expect=2)
            self.assertIn("checkout is not unchanged", rejected.stderr)
            state, _ = ledger.load_state(paths)
            self.assertEqual("active", ledger.attempt_by_id(state, "A-blocked")["lease"]["state"])

    def _replace_blocked_return(self, state: dict[str, object], paths: dict[str, Path], *, status: str, files: list[dict[str, str]]) -> None:
        attempt = ledger.attempt_by_id(state, "A-blocked")
        payload = ledger.stored_payload(paths, attempt["return_ref"], "blocked test return")
        payload["status"] = status
        payload["files"] = files
        replacement = ledger.object_store(paths, ledger.canonical_bytes(payload))
        attempt["return_ref"] = f"objects/{replacement}"

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
            self.assertEqual("AUTH-1", attempt["repair_authorization_ref"])
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

    def test_create_repair_modify_repair_modify_lineage_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, paths, candidate, repair = self.seed_completed_repair_chain(root, completed_repairs=1)
            packet = self.worker_packet(root, "A-repair-2", mode="repair", base=candidate, repair=repair)
            self.dispatch(control, packet, "A-repair-2", 3)
            state, _ = ledger.load_state(paths)
            provenance = ledger.attempt_by_id(state, "A-repair-2")["repair_lease_provenance"]
            self.assertEqual("A-repair-1", provenance["source_attempt_ref"])
            self.assertEqual(["create", "modify"], [item["operation"] for item in provenance["lineage"][0]["attempts"]])
            self.assertEqual(["A-create", "A-repair-1"], [item["attempt_ref"] for item in provenance["lineage"][0]["attempts"]])

    def test_multiple_sequential_legitimate_repairs_preserve_full_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, paths, candidate, repair = self.seed_completed_repair_chain(root, completed_repairs=4)
            packet = self.worker_packet(root, "A-repair-5", mode="repair", base=candidate, repair=repair)
            self.dispatch(control, packet, "A-repair-5", 3)
            state, _ = ledger.load_state(paths)
            lineage = ledger.attempt_by_id(state, "A-repair-5")["repair_lease_provenance"]["lineage"][0]["attempts"]
            self.assertEqual(["create", "modify", "modify", "modify", "modify"], [item["operation"] for item in lineage])
            self.assertEqual(["AUTH-1", "AUTH-2", "AUTH-3", "AUTH-4"], [item["authorization_ref"] for item in lineage[1:]])

    def test_repair_lineage_can_cross_an_authorized_candidate_that_preserved_the_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, paths, candidate, repair = self.seed_completed_repair_chain(root, completed_repairs=1)
            state, previous = ledger.load_state(paths)
            state["tickets"][0]["zone"].append({"path": "side.txt", "operations": ["modify"]})
            intermediate = ledger.attempt_by_id(state, "A-repair-1")
            returned = ledger.stored_payload(paths, intermediate["return_ref"], "test intermediate return")
            returned["files"] = [{"path": "side.txt", "operation": "modify"}]
            replacement = ledger.object_store(paths, ledger.canonical_bytes(returned))
            intermediate["return_ref"] = f"objects/{replacement}"
            intermediate["lease"]["zone"] = [{"path": "side.txt", "operations": ["modify"]}]
            intermediate.pop("repair_lease_provenance")
            state["revision"] = 3
            state["previous_publication_hash"] = ledger.sha256_bytes(previous)
            ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
            packet = self.worker_packet(root, "A-repair-2", mode="repair", base=candidate, repair=repair)
            self.dispatch(control, packet, "A-repair-2", 3)
            final, _ = ledger.load_state(paths)
            lineage = ledger.attempt_by_id(final, "A-repair-2")["repair_lease_provenance"]["lineage"][0]["attempts"]
            self.assertEqual(["create", "preserve"], [item["operation"] for item in lineage])

    def test_transitive_repair_rejects_stale_and_forked_candidate_chain(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, _, _, repair = self.seed_completed_repair_chain(root, completed_repairs=1)
            packet = self.worker_packet(root, "A-stale-chain", mode="repair", base="b" * 40, repair=repair)
            rejected = self.dispatch(control, packet, "A-stale-chain", 3, expect=2)
            self.assertIn("stale or forked", rejected.stderr)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, paths, candidate, repair = self.seed_completed_repair_chain(root, completed_repairs=1)
            state, previous = ledger.load_state(paths)
            ledger.attempt_by_id(state, "A-repair-1")["repair_lease_provenance"]["candidate_sha"] = "f" * 40
            state["revision"] = 3
            state["previous_publication_hash"] = ledger.sha256_bytes(previous)
            ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
            packet = self.worker_packet(root, "A-forked-chain", mode="repair", base=candidate, repair=repair)
            rejected = self.dispatch(control, packet, "A-forked-chain", 3, expect=2)
            self.assertIn("broken create-to-modify provenance edge", rejected.stderr)

    def test_transitive_repair_rejects_foreign_path_and_ticket(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, _, candidate, repair = self.seed_completed_repair_chain(root, completed_repairs=1)
            packet = self.worker_packet(root, "A-foreign-path", mode="repair", base=candidate, path="other.txt", repair=repair)
            rejected = self.dispatch(control, packet, "A-foreign-path", 3, expect=2)
            self.assertIn("lacks prior-create provenance", rejected.stderr)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, paths, candidate, repair = self.seed_completed_repair_chain(root, completed_repairs=1)
            state, previous = ledger.load_state(paths)
            ledger.attempt_by_id(state, "A-create")["subject_ref"] = "T-foreign"
            state["revision"] = 3
            state["previous_publication_hash"] = ledger.sha256_bytes(previous)
            ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
            packet = self.worker_packet(root, "A-foreign-ticket", mode="repair", base=candidate, repair=repair)
            rejected = self.dispatch(control, packet, "A-foreign-ticket", 3, expect=2)
            self.assertIn("foreign", rejected.stderr)

    def test_transitive_repair_rejects_missing_original_validated_create(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, paths, candidate, repair = self.seed_completed_repair_chain(root, completed_repairs=1)
            state, previous = ledger.load_state(paths)
            origin = ledger.attempt_by_id(state, "A-create")
            returned = ledger.stored_payload(paths, origin["return_ref"], "test origin return")
            returned["files"][0]["operation"] = "modify"
            replacement = ledger.object_store(paths, ledger.canonical_bytes(returned))
            origin["return_ref"] = f"objects/{replacement}"
            state["revision"] = 3
            state["previous_publication_hash"] = ledger.sha256_bytes(previous)
            ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
            packet = self.worker_packet(root, "A-no-create", mode="repair", base=candidate, repair=repair)
            rejected = self.dispatch(control, packet, "A-no-create", 3, expect=2)
            self.assertIn("original validated create", rejected.stderr)

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

    def test_legacy_quarantined_repair_reconciles_once_with_full_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); control, _, paths, baseline, candidate = self.seed_legacy_quarantined_repair(root)
            first = json.loads(self.reconcile_legacy(control, None, candidate).stdout)
            self.assertFalse(first["idempotent"])
            self.assertEqual(["app.txt"], first["changed_paths"])
            state, _ = ledger.load_state(paths)
            attempt = ledger.attempt_by_id(state, "A-repair")
            self.assertEqual("active", attempt["lease"]["state"])
            self.assertEqual([{"path": "app.txt", "operations": ["modify"]}], attempt["lease"]["zone"])
            self.assertEqual("A-create", attempt["repair_lease_provenance"]["source_attempt_ref"])
            receipt = ledger.stored_payload(paths, attempt["quarantine_reconciliation_ref"], "test receipt")
            self.assertEqual("test-operator", receipt["actor"])
            self.assertEqual(candidate, receipt["candidate_sha"])
            self.assertEqual("git_base", receipt["baseline_source"])
            self.assertTrue(receipt["write_set_audit"]["pass"])
            self.assertEqual("advisory", state["issues"][0]["impact"])
            repeated = json.loads(self.reconcile_legacy(control, None, candidate).stdout)
            self.assertTrue(repeated["idempotent"])
            repeated_state, _ = ledger.load_state(paths)
            self.assertEqual(state["revision"], repeated_state["revision"])

    def test_quarantine_reconciliation_rejects_stale_base_and_foreign_write_set(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); control, _, paths, baseline, candidate = self.seed_legacy_quarantined_repair(root)
            rejected = self.reconcile_legacy(control, baseline, candidate, base="d" * 40, expect=2)
            self.assertIn("base SHA is stale", rejected.stderr)
            state, _ = ledger.load_state(paths)
            self.assertEqual("quarantined", ledger.attempt_by_id(state, "A-repair")["lease"]["state"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); control, _, paths, baseline, candidate = self.seed_legacy_quarantined_repair(root, foreign_change=True)
            rejected = self.reconcile_legacy(control, baseline, candidate, expect=2)
            self.assertIn("write-set audit failed", rejected.stderr)
            state, _ = ledger.load_state(paths)
            self.assertEqual("quarantined", ledger.attempt_by_id(state, "A-repair")["lease"]["state"])

    def test_quarantine_reconciliation_rejects_non_write_set_quarantine(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); control, _, paths, baseline, candidate = self.seed_legacy_quarantined_repair(root, issue_type="attempt_termination")
            rejected = self.reconcile_legacy(control, baseline, candidate, expect=2)
            self.assertIn("non-write-set blocking causes", rejected.stderr)
            state, _ = ledger.load_state(paths)
            self.assertEqual("quarantined", ledger.attempt_by_id(state, "A-repair")["lease"]["state"])

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
