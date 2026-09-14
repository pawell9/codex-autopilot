#!/usr/bin/env python3
"""Current-surface disposable probes for the final V1 qualification pass.

This file is a qualification runner, not production orchestration.  It only
uses temporary roots and stops after the first new local implementation
defect, as required by the release protocol.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import ledger


ROOT = Path(__file__).resolve().parents[1]
CLI = ["python3", str(ROOT / "tools" / "ledger.py")]


def write_json(path: Path, value: object) -> None:
    ledger.atomic_write(path, ledger.canonical_bytes(value))


def run(*args: str, cwd: Path | None = None, expect: int = 0) -> dict[str, object]:
    proc = subprocess.run([*CLI, *args], cwd=cwd, text=True, capture_output=True)
    return {
        "argv": [*CLI, *args],
        "cwd": str(cwd) if cwd else None,
        "exit": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "expected_exit": expect,
        "matched_expected": proc.returncode == expect,
    }


def shell(*args: str, cwd: Path, expect: int = 0) -> dict[str, object]:
    proc = subprocess.run(list(args), cwd=cwd, text=True, capture_output=True)
    return {
        "argv": list(args),
        "cwd": str(cwd),
        "exit": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "expected_exit": expect,
        "matched_expected": proc.returncode == expect,
    }


def fresh(root: Path, name: str, *, phase: str = "EXECUTE") -> tuple[Path, Path, str]:
    control = root / f"{name}-control"
    repo = root / f"{name}-repo"
    control.mkdir()
    repo.mkdir()
    result = run("init", "--control-root", str(control), "--repo-root", str(repo), "--run-id", name, "--owner-token", "owner-a")
    assert result["matched_expected"], result
    seed(control, repo, name, phase=phase)
    return control, repo, name


def seed(control: Path, repo: Path, run_id: str, *, phase: str = "EXECUTE") -> None:
    paths = ledger.paths(control, run_id)
    state, previous = ledger.load_state(paths)
    intent = paths["docs"] / "intent" / "v1.md"
    ledger.atomic_write(intent, f"# {run_id}\n\nDeterministic micro-project intent v1.\n".encode())
    document_hash = ledger.sha256_file(intent)
    state["repository"].update({"branch": "main", "checkout": str(repo), "initial_head": None})
    state["documents"] = [{"id": "D-1", "version": "v1", "path": str(intent), "hash": document_hash, "kind": "intent", "section_anchors": []}]
    state["intent"] = {"current_revision": "v1", "document_ref": "D-1", "document_hash": document_hash, "approved_amendments": [], "acceptance_policy": "user_assisted", "checkpoint_policy": "gate", "prior_accepted_refs": []}
    state["requirements"] = [{"id": "R-1", "version": "v1", "status": "active", "provenance_refs": ["D-1"], "criterion_refs": ["C-1"], "decision_ref": None}]
    state["criteria"] = [{"id": "C-1", "version": "v1", "requirement_refs": ["R-1"], "oracle": "deterministic record-count oracle", "status": "active", "source_ref": "D-1"}]
    state["contracts"] = [{"id": "K-1", "version": "v1", "status": "active", "provenance_refs": ["D-1"], "producer_refs": [], "consumer_refs": ["C-1"]}]
    state["tickets"] = [{"id": "T-1", "goal_ref": "G-1", "criterion_refs": ["C-1"], "contract_refs": ["K-1"], "dependency_refs": [], "state": "READY", "verification_ref": "deterministic-oracle", "complexity": "bounded", "risk": "routine", "zone": [{"path": "app.py", "operations": ["modify", "create"]}], "current_attempt": None, "replacement_refs": []}]
    state["lifecycle"] = {"phase": phase, "control": "ACTIVE", "reason": "qualification_fixture", "issue_refs": [], "stop_target": None, "next_action": {"kind": "qualification", "subject_refs": [], "preconditions": [], "read_refs": ["design/01-lifecycle-state-machine.md"]}}
    state["revision"] = 1
    state["previous_publication_hash"] = ledger.sha256_bytes(previous)
    ledger.validate_ledger(state)
    ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))


def baseline_manifest(repo: Path) -> Path:
    files: list[dict[str, object]] = []
    for path in sorted(repo.rglob("*")):
        rel = path.relative_to(repo)
        if ".git" in rel.parts or path.is_symlink() or not path.is_file():
            continue
        info = path.lstat()
        files.append({"path": rel.as_posix(), "type": "file", "mode": stat.S_IMODE(info.st_mode), "sha256": ledger.sha256_file(path)})
    target = repo.parent / "baseline.json"
    write_json(target, {"files": files})
    return target


def packet(run_id: str, attempt_id: str, repo: Path, base: str | None = None) -> Path:
    target = repo.parent / f"{attempt_id}-packet.json"
    write_json(target, {"identity": {"run_id": run_id, "ticket_id": "T-1", "attempt_id": attempt_id, "epoch": 0}, "kind": "worker", "mode": "implement", "goal": "qualification worker", "acceptance": [{"criterion_id": "C-1"}], "workspace": {"root": str(repo), "expected_base": base}, "write": {"allow": [{"path": "app.py", "operations": ["modify", "create"]}]}, "verification": [{"check_id": "oracle", "required": True}], "risk": {"level": "routine"}, "context": [{"ref": "contracts/worker.md"}], "return_target": {"transport": "file", "path": "return.json"}})
    return target


def dispatch_and_return(control: Path, repo: Path, run_id: str, attempt_id: str, *, status: str = "DONE", issue: bool = False) -> tuple[dict[str, object], Path]:
    paths = ledger.paths(control, run_id)
    state, _ = ledger.load_state(paths)
    p = packet(run_id, attempt_id, repo)
    route = repo.parent / f"{attempt_id}-route.json"
    write_json(route, {"id": f"route-{attempt_id}", "capability": "worker", "reasoning": "bounded disposable qualification", "adequacy": "CONFIRMED", "context_grade": "PACKET_SCOPED"})
    dispatched = run("dispatch", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-a", "--revision", str(state["revision"]), "--ticket-id", "T-1", "--attempt-id", attempt_id, "--lease-id", f"L-{attempt_id}", "--route-id", f"route-{attempt_id}", "--packet", str(p), "--route", str(route))
    state, _ = ledger.load_state(paths)
    attempt = next(a for a in state["attempts"] if a["id"] == attempt_id)
    inbox = paths["scratch"] / attempt_id / "return.json"
    payload: dict[str, object] = {"identity": {"run_id": run_id, "ticket_id": "T-1", "attempt_id": attempt_id, "packet_hash": attempt["packet_hash"], "epoch": 0}, "status": status, "result": "qualification return", "files": [{"path": "app.py", "operation": "modify"}], "checks": [{"check_id": "oracle", "outcome": "pass" if status == "DONE" else "not_run", "actual": "fixture", "evidence_ref": "EV-worker"}], "criteria": [{"criterion_id": "C-1", "outcome": "satisfied" if status == "DONE" else "unverifiable", "evidence_refs": ["EV-worker"]}]}
    if issue:
        payload["issues"] = [{"type": "contract_gap", "cause": "contract", "impact": "blocking", "affected_refs": ["T-1"], "disposition": "repair contract"}]
    write_json(inbox, payload)
    ingested = run("ingest-return", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-a", "--revision", str(state["revision"]), "--attempt-id", attempt_id, "--return-file", str(inbox), "--kind", "worker")
    return {"dispatch": dispatched, "ingest": ingested}, inbox


def e04b(root: Path) -> dict[str, object]:
    observations: list[object] = []
    repo = root / "audit-repo"
    repo.mkdir()
    shell("git", "init", "-q", cwd=repo)
    (repo / ".gitignore").write_text("ignored.out\n", encoding="utf-8")
    (repo / "app.txt").write_text("BASE\n", encoding="utf-8")
    (repo / "foreign.txt").write_text("FOREIGN\n", encoding="utf-8")
    shell("git", "add", ".gitignore", "app.txt", "foreign.txt", cwd=repo)
    shell("git", "-c", "user.name=Qualification", "-c", "user.email=qualification@example.invalid", "commit", "-qm", "baseline", cwd=repo)
    baseline = baseline_manifest(repo)
    (repo / "foreign.txt").write_text("FOREIGN-MODIFIED\n", encoding="utf-8")
    (repo / "untracked.txt").write_text("UNTRACKED\n", encoding="utf-8")
    (repo / "ignored.out").write_text("IGNORED\n", encoding="utf-8")
    (repo / "escape").symlink_to("/tmp")
    declared = repo.parent / "declared.json"; zone = repo.parent / "zone.json"
    write_json(declared, [{"path": "app.txt"}]); write_json(zone, [{"path": "app.txt", "operations": ["modify"]}])
    audit = run("audit-write-set", "--root", str(repo), "--baseline", str(baseline), "--declared", str(declared), "--zone", str(zone))
    audit_payload = json.loads(str(audit["stdout"]))
    audit_pass = audit["matched_expected"] and not audit_payload["pass"] and "ignored.out" in audit_payload["actual_paths"] and "escape" in {item["path"] for item in audit_payload["unsafe_paths"]}
    observations.append({"dirty_audit": audit, "pass_conditions": {"ignored_observed": "ignored.out" in audit_payload["actual_paths"], "escape_symlink_rejected": "escape" in {item["path"] for item in audit_payload["unsafe_paths"]}, "audit_pass": audit_payload["pass"]}, "qualified": audit_pass})

    control, worker_repo, run_id = fresh(root, "E04b-worker")
    worker_repo.mkdir(exist_ok=True) if not worker_repo.exists() else None
    partial, _ = dispatch_and_return(control, worker_repo, run_id, "A-blocked", status="BLOCKED", issue=True)
    state, _ = ledger.load_state(ledger.paths(control, run_id))
    receipt = root / "blocked-receipt.json"; write_json(receipt, {"status": "PASS", "commit_sha": "0" * 40, "tree_sha": "1" * 40})
    candidate = run("candidate", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-a", "--revision", str(state["revision"]), "--attempt-id", "A-blocked", "--commit-receipt", str(receipt), "--operation-id", "OP-missing", expect=2)
    final_state, _ = ledger.load_state(ledger.paths(control, run_id))
    observations.append({"partial_worker": partial, "blocked_candidate_rejected": candidate, "ticket_state": final_state["tickets"][0]["state"], "qualified": partial["ingest"]["matched_expected"] and candidate["matched_expected"] and final_state["tickets"][0]["state"] == "BLOCKED"})

    effect_control, effect_repo, effect_run = fresh(root, "E04b-effect")
    shell("git", "init", "-q", cwd=effect_repo)
    (effect_repo / "app.txt").write_text("BASE\n", encoding="utf-8")
    shell("git", "add", "app.txt", cwd=effect_repo); shell("git", "-c", "user.name=Qualification", "-c", "user.email=qualification@example.invalid", "commit", "-qm", "base", cwd=effect_repo)
    base = shell("git", "rev-parse", "HEAD", cwd=effect_repo)["stdout"]
    prep = run("prepare-effect", "--control-root", str(effect_control), "--run-id", effect_run, "--owner-token", "owner-a", "--revision", "1", "--operation-id", "OP-1", "--kind", "candidate_commit", "--target", str(effect_repo), "--expected-before", base, "--authority-ref", "qualification")
    (effect_repo / "app.txt").write_text("VALUE=42\n", encoding="utf-8"); shell("git", "add", "app.txt", cwd=effect_repo); shell("git", "-c", "user.name=Qualification", "-c", "user.email=qualification@example.invalid", "commit", "-qm", "candidate", cwd=effect_repo)
    head = shell("git", "rev-parse", "HEAD", cwd=effect_repo)["stdout"]; tree = shell("git", "rev-parse", "HEAD^{tree}", cwd=effect_repo)["stdout"]
    receipt = root / "effect-receipt.json"; write_json(receipt, {"operation_id": "OP-1", "target": str(effect_repo), "base_sha": base, "commit_sha": head, "tree_sha": tree, "status": "PASS", "result": "commit observed"})
    applied = run("reconcile-effect", "--control-root", str(effect_control), "--run-id", effect_run, "--owner-token", "owner-a", "--revision", "2", "--operation-id", "OP-1", "--result", "applied", "--receipt", str(receipt))
    duplicate = run("reconcile-effect", "--control-root", str(effect_control), "--run-id", effect_run, "--owner-token", "owner-a", "--revision", "3", "--operation-id", "OP-1", "--result", "applied", "--receipt", str(receipt), expect=2)
    observations.append({"effect_reconciliation": {"prepare": prep, "applied": applied, "duplicate": duplicate, "head_after": shell("git", "rev-parse", "HEAD", cwd=effect_repo)["stdout"]}, "qualified": prep["matched_expected"] and applied["matched_expected"] and duplicate["matched_expected"]})
    wrong = root / "wrong-receipt.json"; write_json(wrong, {"operation_id": "OP-1", "target": str(root / "other-repo"), "status": "PASS", "result": "wrong target"})
    wrong_target = run("reconcile-effect", "--control-root", str(effect_control), "--run-id", effect_run, "--owner-token", "owner-a", "--revision", "3", "--operation-id", "OP-1", "--result", "applied", "--receipt", str(wrong), expect=2)
    observations.append({"wrong_root_receipt_rejected": wrong_target, "qualified": wrong_target["matched_expected"]})

    hook_repo = root / "hook-repo"; hook_repo.mkdir(); shell("git", "init", "-q", cwd=hook_repo)
    (hook_repo / "app.txt").write_text("BASE\n", encoding="utf-8"); shell("git", "add", "app.txt", cwd=hook_repo); shell("git", "-c", "user.name=Qualification", "-c", "user.email=qualification@example.invalid", "commit", "-qm", "base", cwd=hook_repo)
    hook_baseline = baseline_manifest(hook_repo); hook = hook_repo / ".git" / "hooks" / "post-commit"; hook.write_text("#!/bin/sh\nprintf 'HOOK\n' > hook-mutated.txt\n", encoding="utf-8"); hook.chmod(0o755)
    (hook_repo / "app.txt").write_text("VALUE=42\n", encoding="utf-8"); shell("git", "add", "app.txt", cwd=hook_repo); hook_commit = shell("git", "-c", "user.name=Qualification", "-c", "user.email=qualification@example.invalid", "commit", "-qm", "hooked", cwd=hook_repo)
    hook_audit = run("audit-write-set", "--root", str(hook_repo), "--baseline", str(hook_baseline), "--declared", str(declared), "--zone", str(zone))
    hook_payload = json.loads(str(hook_audit["stdout"]))
    observations.append({"hook_mutation": {"commit": hook_commit, "audit": hook_audit, "hook_path_caught": "hook-mutated.txt" in hook_payload["changed_paths"]}, "qualified": hook_audit["matched_expected"] and not hook_payload["pass"]})

    clean_repo = root / "clean-repo"; clean_repo.mkdir(); shell("git", "init", "-q", cwd=clean_repo); (clean_repo / ".gitignore").write_text("ignored.out\n", encoding="utf-8"); (clean_repo / "tracked.txt").write_text("BASE\n", encoding="utf-8"); shell("git", "add", ".gitignore", "tracked.txt", cwd=clean_repo); shell("git", "-c", "user.name=Qualification", "-c", "user.email=qualification@example.invalid", "commit", "-qm", "base", cwd=clean_repo)
    (clean_repo / "untracked.txt").write_text("U\n", encoding="utf-8"); (clean_repo / "ignored.out").write_text("I\n", encoding="utf-8"); clean_fd = shell("git", "clean", "-fd", cwd=clean_repo); clean_fd_state = {"untracked_exists": (clean_repo / "untracked.txt").exists(), "ignored_exists": (clean_repo / "ignored.out").exists()}
    (clean_repo / "untracked.txt").write_text("U\n", encoding="utf-8"); clean_fdx = shell("git", "clean", "-fdx", cwd=clean_repo); clean_fdx_state = {"untracked_exists": (clean_repo / "untracked.txt").exists(), "ignored_exists": (clean_repo / "ignored.out").exists()}
    (clean_repo / "untracked.txt").write_text("U\n", encoding="utf-8"); stash_u = shell("git", "stash", "push", "-u", "-qm", "stash-u", cwd=clean_repo); stash_u_state = {"untracked_exists": (clean_repo / "untracked.txt").exists()}
    (clean_repo / "ignored.out").write_text("I\n", encoding="utf-8"); stash_all = shell("git", "stash", "push", "--all", "-qm", "stash-all", cwd=clean_repo); stash_all_state = {"ignored_exists": (clean_repo / "ignored.out").exists()}
    observations.append({"disposable_clean_stash": {"clean_fd": clean_fd, "clean_fd_state": clean_fd_state, "clean_fdx": clean_fdx, "clean_fdx_state": clean_fdx_state, "stash_u": stash_u, "stash_u_state": stash_u_state, "stash_all": stash_all, "stash_all_state": stash_all_state}, "qualified": all([clean_fd["matched_expected"], not clean_fd_state["untracked_exists"], clean_fd_state["ignored_exists"], clean_fdx["matched_expected"], not clean_fdx_state["ignored_exists"], stash_u["matched_expected"], not stash_u_state["untracked_exists"], stash_all["matched_expected"], not stash_all_state["ignored_exists"]])})

    cancel_control, cancel_repo, cancel_run = fresh(root, "E04b-cancel")
    foreign = cancel_repo / "foreign.txt"; foreign.write_text("preserve\n", encoding="utf-8")
    quiesce = run("cancel", "--control-root", str(cancel_control), "--run-id", cancel_run, "--owner-token", "owner-a", "--revision", "1", "--stop-target", "qualification")
    stop = root / "stop.json"; write_json(stop, {"status": "PASS", "writers_stopped": True, "reconciled": True})
    cancelled = run("cancel", "--control-root", str(cancel_control), "--run-id", cancel_run, "--owner-token", "owner-a", "--revision", "strange", "--finalize", "--stop-evidence", str(stop), expect=2)
    state, _ = ledger.load_state(ledger.paths(cancel_control, cancel_run)); cancelled = run("cancel", "--control-root", str(cancel_control), "--run-id", cancel_run, "--owner-token", "owner-a", "--revision", str(state["revision"]), "--finalize", "--stop-evidence", str(stop))
    observations.append({"cancel_preserves_foreign": {"quiesce": quiesce, "finalize": cancelled, "control": ledger.load_state(ledger.paths(cancel_control, cancel_run))[0]["lifecycle"]["control"], "foreign_preserved": foreign.read_text(encoding="utf-8") == "preserve\n"}, "qualified": quiesce["matched_expected"] and cancelled["matched_expected"] and foreign.exists()})
    recovery_control, recovery_repo, recovery_run = fresh(root, "E04b-recovery")
    takeover = run("recover", "--control-root", str(recovery_control), "--run-id", recovery_run, "--owner-token", "owner-a", "--revision", "1", "--takeover", "--new-owner-token", "owner-b", "--attestation-ref", "qualification")
    recovery_state, _ = ledger.load_state(ledger.paths(recovery_control, recovery_run))
    observations.append({"fresh_takeover_recovery": takeover, "control": recovery_state["lifecycle"]["control"], "epoch": recovery_state["owner"]["epoch"], "qualified": takeover["matched_expected"] and recovery_state["lifecycle"]["control"] == "RECOVERING"})
    return {"experiment": "E04b", "observations": observations, "qualified": all(item.get("qualified") for item in observations)}


def e07_pause_guard(root: Path) -> dict[str, object]:
    control, repo, run_id = fresh(root, "E07", phase="PREFLIGHT")
    (repo / "records.csv").write_text("ok\nmalformed\nedge\n", encoding="utf-8")
    (repo / "app.py").write_text("print('2')\n", encoding="utf-8")
    shell("git", "init", "-q", cwd=repo); shell("git", "add", "records.csv", "app.py", cwd=repo); shell("git", "-c", "user.name=Qualification", "-c", "user.email=qualification@example.invalid", "commit", "-qm", "micro-project-base", cwd=repo)
    transitions = []
    for phase in ("INTENT", "DESIGN", "PLAN", "EXECUTE"):
        state, _ = ledger.load_state(ledger.paths(control, run_id))
        transitions.append(run("gate", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-a", "--revision", str(state["revision"]), "--phase", phase, "--control", "ACTIVE", "--next-action", f"e07-{phase.lower()}"))
    state, _ = ledger.load_state(ledger.paths(control, run_id)); dispatch_result, _ = dispatch_and_return(control, repo, run_id, "A-E07")
    state, _ = ledger.load_state(ledger.paths(control, run_id))
    prepare = run("prepare-effect", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-a", "--revision", str(state["revision"]), "--operation-id", "OP-E07", "--kind", "candidate_commit", "--target", str(repo), "--authority-ref", "qualification")
    (repo / "app.py").write_text("print('2')\n# prepared candidate\n", encoding="utf-8"); shell("git", "add", "app.py", cwd=repo); shell("git", "-c", "user.name=Qualification", "-c", "user.email=qualification@example.invalid", "commit", "-qm", "prepared-candidate", cwd=repo)
    state, _ = ledger.load_state(ledger.paths(control, run_id))
    pause = run("gate", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-a", "--revision", str(state["revision"]), "--control", "PAUSED", "--next-action", "resume-e07")
    paused_state, _ = ledger.load_state(ledger.paths(control, run_id))
    violation = {"pause_command_accepted": pause["matched_expected"], "control": paused_state["lifecycle"]["control"], "active_attempts": [{"id": a["id"], "state": a["state"], "lease": a["lease"]["state"]} for a in paused_state.get("attempts", []) if a["state"] in ("PREPARED", "DISPATCHED", "RETURNED")], "prepared_operations": [{"id": op["id"], "state": op["state"]} for op in paused_state.get("operations", []) if op["state"] in ("prepared", "uncertain")], "required": "pause must first quiesce and obtain stop/reconciliation evidence before PAUSED"}
    return {"experiment": "E07", "stopped_at": "pause_after_prepared_commit", "transitions": transitions, "dispatch_and_return": dispatch_result, "prepare_effect": prepare, "pause_observation": violation, "new_local_defect": pause["matched_expected"] and paused_state["lifecycle"]["control"] == "PAUSED" and bool(violation["active_attempts"]) and bool(violation["prepared_operations"]), "defect": "cmd_gate permits ACTIVE -> PAUSED with an active attempt and prepared candidate effect; it bypasses the required QUIESCING stop/reconciliation guard."}


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="codex-autopilot-v1-final-") as directory:
        root = Path(directory)
        e04 = e04b(root)
        result: dict[str, object] = {"package": {"ledger_sha256": ledger.sha256_file(ROOT / "tools" / "ledger.py"), "schema_sha256": ledger.sha256_file(ROOT / "schemas" / "contracts.schema.json")}, "disposable_root": str(root), "e04b": e04}
        if not e04["qualified"]:
            result["verdict"] = "V1 RELEASE BLOCKED"
            result["stop_reason"] = "E04b failed"
        else:
            e07 = e07_pause_guard(root)
            result["e07"] = e07
            if e07["new_local_defect"]:
                result["verdict"] = "V1 RELEASE BLOCKED"
                result["stop_reason"] = "new local implementation defect in E07 pause guard; E09 not run"
            else:
                result["verdict"] = "E07 pause arm did not reproduce the expected defect; continue with E09 manually"
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
