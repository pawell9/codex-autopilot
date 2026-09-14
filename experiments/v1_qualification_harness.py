#!/usr/bin/env python3
"""Resumable black-box qualification probes for the V1 ledger/helper.

The harness owns only disposable fixtures under /private/tmp.  It never
touches E03-M or E10 and never installs anything globally.  Each invocation
prints JSON with raw observations; reports in experiments/ are the authority
for conclusions.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "tools" / "ledger.py"
RUN_ROOT = Path("/private/tmp/codex-autopilot-v1-qualification-20260913")
sys.path.insert(0, str(ROOT / "tools"))
from ledger import atomic_write, canonical_bytes, load_state, paths, sha256_bytes, validate_ledger  # noqa: E402


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, canonical_bytes(value))


def cmd(args: list[str], cwd: Path | None = None, expect: int = 0) -> dict[str, object]:
    proc = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    return {
        "argv": args,
        "cwd": str(cwd) if cwd else None,
        "exit": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "expected_exit": expect,
        "matched_expected": proc.returncode == expect,
    }


def fresh(name: str) -> tuple[Path, Path, str]:
    root = RUN_ROOT / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    control = root / "control"
    repo = root / "repo"
    control.mkdir()
    repo.mkdir()
    run_id = name
    cmd([sys.executable, str(LEDGER), "init", "--control-root", str(control), "--repo-root", str(repo), "--run-id", run_id, "--owner-token", "owner-a"])
    return control, repo, run_id


def state_paths(control: Path, run_id: str) -> dict[str, Path]:
    return paths(control, run_id)


def seed_run(control: Path, repo: Path, run_id: str, *, tickets: list[dict[str, object]] | None = None, criteria: list[dict[str, object]] | None = None, intent_revision: str = "intent-v1") -> None:
    p = state_paths(control, run_id)
    state, previous = load_state(p)
    seeded = copy.deepcopy(state)
    intent_bytes = f"# {run_id}\n\nIntent {intent_revision}.\n".encode()
    intent_path = p["docs"] / "intent" / f"{intent_revision}.md"
    atomic_write(intent_path, intent_bytes)
    seeded["repository"].update({"initial_head": None, "branch": "main", "checkout": str(repo)})
    seeded["documents"] = [{"id": "doc-intent", "version": intent_revision, "path": str(intent_path), "hash": digest(intent_bytes), "kind": "intent", "section_anchors": []}]
    seeded["intent"] = {"current_revision": intent_revision, "document_ref": "doc-intent", "approved_amendments": [], "acceptance_policy": "user_assisted", "checkpoint_policy": "gate", "prior_accepted_refs": []}
    seeded["requirements"] = [{"id": "R-1", "version": "v1", "status": "active", "provenance_refs": ["doc-intent:v1"], "criterion_refs": ["C-1"], "decision_ref": None}]
    seeded["criteria"] = criteria or [{"id": "C-1", "version": "v1", "requirement_refs": ["R-1"], "oracle": "fixture oracle", "status": "active", "source_ref": "doc-intent:v1"}]
    seeded["contracts"] = [{"id": "contract-v1", "version": "v1", "status": "active", "provenance_refs": ["doc-intent:v1"], "producer_refs": [], "consumer_refs": ["C-1"]}]
    seeded["tickets"] = tickets or [{"id": "T-1", "goal_ref": "G-1", "criterion_refs": ["C-1"], "contract_refs": ["contract-v1"], "dependency_refs": [], "state": "READY", "verification_ref": "fixture", "complexity": "bounded", "risk": "routine", "zone": [{"path": "app.txt", "operations": ["modify"]}], "current_attempt": None, "replacement_refs": []}]
    seeded["lifecycle"] = {"phase": "EXECUTE", "control": "ACTIVE", "reason": "fixture_seeded", "issue_refs": [], "stop_target": None, "next_action": {"kind": "dispatch_worker", "subject_refs": [t["id"] for t in seeded["tickets"]], "preconditions": [], "read_refs": ["phases/execute.md"]}}
    seeded["revision"] = 1
    seeded["previous_publication_hash"] = sha256_bytes(previous)
    validate_ledger(seeded)
    atomic_write(p["ledger"], canonical_bytes(seeded))


def packet(run_id: str, ticket_id: str = "T-1", attempt_id: str = "A-1", kind: str = "worker") -> dict[str, object]:
    identity = {"run_id": run_id, "ticket_id": ticket_id, "attempt_id": attempt_id, "epoch": 0}
    if kind == "worker":
        return {"identity": identity, "kind": "worker", "mode": "implement", "goal": "fixture goal", "acceptance": [{"criterion_id": "C-1"}], "workspace": {"root": "", "expected_base": None}, "write": {"allow": ["app.txt"]}, "verification": [{"check_id": "oracle"}], "risk": {"risk": "routine"}, "context": [{"ref": "contracts/worker.md"}], "return_target": {"path": "return.json"}}
    return {"identity": identity, "kind": kind, "mandate": "independent fixture review", "subject_fingerprint": "candidate", "criteria": [{"criterion_id": "C-1"}], "return_target": {"path": "return.json"}}


def dispatch(control: Path, repo: Path, run_id: str, ticket_id: str = "T-1", attempt_id: str = "A-1", route: dict[str, object] | None = None, token: str = "owner-a") -> tuple[dict[str, object], Path]:
    p = state_paths(control, run_id)
    packet_path = RUN_ROOT / run_id / f"{attempt_id}-packet.json"
    packet_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(packet_path, packet(run_id, ticket_id, attempt_id))
    route_path = RUN_ROOT / run_id / f"{attempt_id}-route.json"
    if route is not None:
        write_json(route_path, route)
    result = cmd([sys.executable, str(LEDGER), "dispatch", "--control-root", str(control), "--run-id", run_id, "--owner-token", token, "--revision", "1", "--ticket-id", ticket_id, "--attempt-id", attempt_id, "--lease-id", f"L-{attempt_id}", "--route-id", f"route-{attempt_id}", "--packet", str(packet_path), *( ["--route", str(route_path)] if route is not None else [])])
    state, _ = load_state(p)
    attempt = next(a for a in state["attempts"] if a["id"] == attempt_id)
    inbox = p["scratch"] / attempt_id / "return.json"
    return {"dispatch": result, "attempt": attempt}, inbox


def worker_return(control: Path, run_id: str, attempt_id: str, inbox: Path, status: str = "DONE", packet_hash: str | None = None, extra: dict[str, object] | None = None) -> dict[str, object]:
    p = state_paths(control, run_id)
    state, _ = load_state(p)
    attempt = next(a for a in state["attempts"] if a["id"] == attempt_id)
    payload: dict[str, object] = {"identity": {"run_id": run_id, "ticket_id": attempt["subject_ref"], "attempt_id": attempt_id, "packet_hash": packet_hash or attempt["packet_hash"], "epoch": attempt["epoch"]}, "status": status, "result": "fixture return", "files": [], "checks": [{"check_id": "oracle", "outcome": "pass", "actual": "fixture"}], "criteria": [{"criterion_id": "C-1", "outcome": "satisfied", "evidence": "fixture"}]}
    if extra:
        payload.update(extra)
    write_json(inbox, payload)
    return payload


def candidate_receipt(repo: Path, run_id: str, name: str = "app.txt") -> Path:
    (repo / name).write_text("VALUE=42\n", encoding="utf-8")
    cmd(["git", "add", name], cwd=repo)
    commit = cmd(["git", "-c", "user.name=Qualification", "-c", "user.email=qualification@example.invalid", "commit", "-m", f"candidate {run_id}"], cwd=repo)
    if not commit["matched_expected"]:
        raise RuntimeError(commit)
    sha = cmd(["git", "rev-parse", "HEAD"], cwd=repo)["stdout"]
    tree = cmd(["git", "rev-parse", "HEAD^{tree}"], cwd=repo)["stdout"]
    receipt = RUN_ROOT / run_id / "commit-receipt.json"
    write_json(receipt, {"status": "PASS", "checkout": str(repo), "base_sha": "0" * 40, "commit_sha": sha, "tree_sha": tree, "authority_ref": "fixture-authority", "receipt_ref": "fixture-receipt"})
    return receipt


def test_e01() -> dict[str, object]:
    control, repo, run_id = fresh("E01")
    seed_run(control, repo, run_id)
    observations: list[object] = []
    gate = [sys.executable, str(LEDGER), "gate", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-a", "--revision", "1", "--phase", "EXECUTE", "--next-action", "e01-series"]
    observations.append({"valid_gate": cmd(gate)})
    stale = list(gate); stale[stale.index("--owner-token") + 1] = "owner-stale"
    stale[stale.index("--revision") + 1] = "2"
    observations.append({"stale_owner_and_revision": cmd(stale, expect=2)})
    p = state_paths(control, run_id)
    state, raw = load_state(p)
    current_hash = digest(raw)
    observations.append({"revision": state["revision"], "ledger_hash": current_hash, "prev_exists": p["prev"].exists(), "prev_valid": bool(load_state({**p, "ledger": p["prev"]}) if p["prev"].exists() else False)})
    observations.append({"view": cmd([sys.executable, str(LEDGER), "render-view", "--control-root", str(control), "--run-id", run_id]), "view_exists": (p["run"] / "views" / "status.md").exists()})
    original = p["ledger"].read_bytes()
    atomic_write(p["ledger"], b"{corrupt\n")
    corrupt_status = cmd([sys.executable, str(LEDGER), "status", "--control-root", str(control), "--run-id", run_id], expect=2)
    prev_status = cmd([sys.executable, str(LEDGER), "validate", "--file", str(p["prev"]), "--kind", "ledger"])
    observations.append({"corrupt_current": corrupt_status, "valid_previous_checkpoint": prev_status, "recover_command_on_corrupt_current": cmd([sys.executable, str(LEDGER), "recover", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-a", "--revision", "2"], expect=2)})
    atomic_write(p["ledger"], original)
    series = []
    for _ in range(100):
        state, _ = load_state(p)
        args = [sys.executable, str(LEDGER), "gate", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-a", "--revision", str(state["revision"]), "--phase", "EXECUTE", "--next-action", "series"]
        result = cmd(args)
        if not result["matched_expected"]:
            break
        series.append(load_state(p)[0]["revision"])
    observations.append({"series_revisions_completed": len(series), "series_final_revision": series[-1] if series else None, "ledger_bytes": p["ledger"].stat().st_size, "prev_bytes": p["prev"].stat().st_size if p["prev"].exists() else None, "snapshot_files": sorted(str(x.relative_to(p["run"])) for x in p["run"].rglob("*") if x.is_file())})
    return {"experiment": "E01", "observations": observations, "probe_summary": "Publication/fencing/view work; corrupt-current recovery and bounded snapshot retention remain unsupported by the helper surface."}


def test_e04b() -> dict[str, object]:
    control, repo, run_id = fresh("E04b")
    cmd(["git", "init", "-q"], cwd=repo)
    (repo / ".gitignore").write_text("ignored.out\n", encoding="utf-8")
    (repo / "app.txt").write_text("BASE\n", encoding="utf-8")
    (repo / "foreign.txt").write_text("FOREIGN\n", encoding="utf-8")
    cmd(["git", "add", ".gitignore", "app.txt", "foreign.txt"], cwd=repo)
    cmd(["git", "-c", "user.name=Qualification", "-c", "user.email=qualification@example.invalid", "commit", "-m", "baseline"], cwd=repo)
    (repo / "foreign.txt").write_text("FOREIGN-MODIFIED\n", encoding="utf-8")
    (repo / "untracked.txt").write_text("UNTRACKED\n", encoding="utf-8")
    (repo / "ignored.out").write_text("IGNORED\n", encoding="utf-8")
    (repo / "link.txt").symlink_to("foreign.txt")
    baseline = RUN_ROOT / run_id / "baseline.json"; declared = RUN_ROOT / run_id / "declared.json"; zone = RUN_ROOT / run_id / "zone.json"
    write_json(baseline, {"paths": []}); write_json(declared, [{"path": "app.txt"}]); write_json(zone, [{"path": "app.txt", "operations": ["modify"]}])
    audit = cmd([sys.executable, str(LEDGER), "audit-write-set", "--root", str(repo), "--baseline", str(baseline), "--declared", str(declared), "--zone", str(zone)])
    observations = [{"git_status": cmd(["git", "status", "--porcelain=v1"], cwd=repo)}, {"audit": audit}, {"ignored_visible_to_audit": "ignored.out" in audit["stdout"]}, {"symlink_visible_to_audit": "link.txt" in audit["stdout"]}]
    seed_run(control, repo, run_id)
    dispatch_result, inbox = dispatch(control, repo, run_id)
    worker_return(control, run_id, "A-1", inbox)
    observations.append({"dispatch": dispatch_result, "ingest": cmd([sys.executable, str(LEDGER), "ingest-return", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-a", "--revision", "2", "--attempt-id", "A-1", "--return-file", str(inbox), "--kind", "worker"])})
    return {"experiment": "E04b", "observations": observations, "probe_summary": "Dirty tracked/untracked and symlink status is observable; default audit omits ignored output and helper exposes no prepared-effect reconciliation or safe cancel/resume path."}


def test_e05() -> dict[str, object]:
    control, repo, run_id = fresh("E05")
    seed_run(control, repo, run_id)
    route = {"id": "route-A-1", "capability": "write", "reasoning": "standard", "adequacy": "REJECTED", "context_grade": "UNKNOWN", "requested_binding": "unavailable", "observed_binding": None, "fallback_cause": "permission"}
    result, _ = dispatch(control, repo, run_id, route=route)
    state, _ = load_state(state_paths(control, run_id))
    observations = [{"dispatch_rejected_route": result["dispatch"]}, {"route_record": state.get("routes", [None])[-1]}, {"ticket_state_after_REJECTED_route": state["tickets"][0]["state"]}]
    return {"experiment": "E05", "observations": observations, "probe_summary": "The helper records a rejected route and still prepares/runs the ticket; no cause-first routing, no-progress guard, or repair/escalation decision is enforced."}


def prepared_candidate(name: str, *, worker_status: str = "DONE", review: bool = False) -> tuple[Path, Path, str, dict[str, object], Path]:
    control, repo, run_id = fresh(name)
    cmd(["git", "init", "-q"], cwd=repo); (repo / "app.txt").write_text("BASE\n", encoding="utf-8"); cmd(["git", "add", "app.txt"], cwd=repo); cmd(["git", "-c", "user.name=Qualification", "-c", "user.email=qualification@example.invalid", "commit", "-m", "base"], cwd=repo)
    seed_run(control, repo, run_id)
    dispatched, inbox = dispatch(control, repo, run_id)
    worker_return(control, run_id, "A-1", inbox, status=worker_status)
    ingest = cmd([sys.executable, str(LEDGER), "ingest-return", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-a", "--revision", "2", "--attempt-id", "A-1", "--return-file", str(inbox), "--kind", "worker"])
    receipt = candidate_receipt(repo, run_id)
    state, _ = load_state(state_paths(control, run_id))
    candidate = cmd([sys.executable, str(LEDGER), "candidate", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-a", "--revision", str(state["revision"]), "--attempt-id", "A-1", "--commit-receipt", str(receipt), "--operation-id", "OP-1"])
    state, raw = load_state(state_paths(control, run_id))
    return control, repo, run_id, {"dispatch": dispatched, "ingest": ingest, "candidate": candidate, "candidate_sha": state["attempts"][0]["candidate_sha"], "ledger_hash": digest(raw)}, receipt


def test_e06() -> dict[str, object]:
    control, repo, run_id, setup, receipt = prepared_candidate("E06")
    state, raw = load_state(state_paths(control, run_id)); packet_path = RUN_ROOT / run_id / "review-packet.json"; write_json(packet_path, packet(run_id, kind="review"))
    # review packet is prepared only to exercise integrate; the returned review
    # deliberately omits coverage entries and context provenance.
    review_path = state_paths(control, run_id)["scratch"] / "A-1" / "review.json"
    write_json(review_path, {"identity": {"run_id": run_id, "attempt_id": "A-1", "packet_hash": state["attempts"][0]["packet_hash"], "epoch": 0}, "subject_fingerprint": state["attempts"][0]["candidate_sha"], "verdict": "PASS", "coverage": [], "checks": [], "findings": []})
    integrity = RUN_ROOT / run_id / "integrity.json"; write_json(integrity, {"status": "PASS", "candidate_fingerprint": state["attempts"][0]["candidate_sha"], "ledger_hash": digest(raw)})
    integrate = cmd([sys.executable, str(LEDGER), "integrate", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-a", "--revision", str(state["revision"]), "--attempt-id", "A-1", "--review-file", str(review_path), "--integrity-receipt", str(integrity), "--review-id", "REV-1"])
    final, _ = load_state(state_paths(control, run_id))
    return {"experiment": "E06", "observations": [{"setup": setup}, {"integrate_empty_coverage_PASS": integrate}, {"ticket_state_after_review": final["tickets"][0]["state"]}, {"review_record": final.get("reviews", [])[-1] if final.get("reviews") else None}], "probe_summary": "A PASS review with empty coverage/checks and no context refs is integrated; topology/critical-axis/freshness coverage is not enforced."}


def test_e07() -> dict[str, object]:
    control, repo, run_id, setup, receipt = prepared_candidate("E07", worker_status="BLOCKED")
    state, _ = load_state(state_paths(control, run_id))
    observations: list[object] = [{"blocked_worker_candidate_result": setup["candidate"]}]
    export = RUN_ROOT / run_id / "candidate-export"; export.mkdir(); shutil.copy2(repo / "app.txt", export / "app.txt")
    bundle = RUN_ROOT / run_id / "bundle"; packet_path = RUN_ROOT / run_id / "acceptance-packet.json"; projection_path = RUN_ROOT / run_id / "projection.json"
    write_json(packet_path, packet(run_id, kind="acceptance")); write_json(projection_path, {"kind": "acceptance_projection", "intent_revision": "intent-v1", "candidate_fingerprint": state["attempts"][0]["candidate_sha"], "goal": "run fixture", "criteria": [{"id": "C-1", "oracle": "app.txt contains VALUE=42"}], "exclusions": [], "return_schema": "acceptance_return"})
    handoff = cmd([sys.executable, str(LEDGER), "prepare-handoff", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-a", "--revision", str(state["revision"]), "--attempt-id", "A-1", "--packet", str(packet_path), "--projection", str(projection_path), "--export-root", str(export), "--bundle-root", str(bundle)])
    state, raw = load_state(state_paths(control, run_id)); attempt = state["attempts"][0]; manifest = json.loads((bundle / "manifest.json").read_text())
    env = RUN_ROOT / run_id / "environment.json"; context = RUN_ROOT / run_id / "context.json"; ret = state_paths(control, run_id)["scratch"] / "A-1" / "acceptance.json"; integrity = RUN_ROOT / run_id / "g5-integrity.json"
    write_json(env, {"receipt_id": "env-E07", "status": "PASS", "topology": {"surface": "disposable-review-root"}, "inventory_hashes": [{"path": "candidate-export/app.txt", "sha256": digest((export / "app.txt").read_bytes())}], "effective_grants": {"authoritative_repo": False}, "boundary_probes": [{"probe": "authoritative-input", "result": "absent from transferred inputs"}], "authoritative_absent": True})
    write_json(context, {"receipt_id": "ctx-E07", "status": "PASS", "grade": "MANUAL_ATTESTED_CLEAN", "packet_hash": attempt["packet_hash"], "export_hash": manifest and digest((bundle / "manifest.json").read_bytes()), "clean_input": True, "contamination_absent": True, "session_provenance": {"session": "new-disposable-review-process"}})
    write_json(ret, {"identity": {"run_id": run_id, "attempt_id": "A-1", "packet_hash": attempt["packet_hash"], "intent_revision": "intent-v1", "epoch": 0}, "candidate_fingerprint": attempt["candidate_sha"], "verdict": "PASS", "outcomes": [{"criterion_id": "C-1", "outcome": "fulfilled", "evidence_refs": ["oracle-E07"]}], "checks": [{"check_id": "oracle", "outcome": "fulfilled", "actual": "VALUE=42", "evidence_ref": "oracle-E07"}], "findings": []})
    write_json(integrity, {"status": "PASS", "candidate_fingerprint": attempt["candidate_sha"], "ledger_hash": digest(raw)})
    state, _ = load_state(state_paths(control, run_id))
    imp = cmd([sys.executable, str(LEDGER), "import-manual", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-a", "--revision", str(state["revision"]), "--attempt-id", "A-1", "--return-file", str(ret), "--environment-receipt", str(env), "--context-receipt", str(context), "--integrity-receipt", str(integrity), "--intent-revision", "intent-v1", "--candidate-fingerprint", attempt["candidate_sha"], "--required-criteria", "C-1"])
    state, _ = load_state(state_paths(control, run_id)); cancel = cmd([sys.executable, str(LEDGER), "gate", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-a", "--revision", str(state["revision"]), "--control", "CANCELLED", "--next-action", "cancelled"], expect=0)
    observations.extend([{ "handoff": handoff }, {"manual_import": imp}, {"cancel_direct_gate": cancel}])
    return {"experiment": "E07", "observations": observations, "probe_summary": "Manual bundle/import path can reach acceptance, but candidate accepts a BLOCKED worker return and CANCELLED is directly writable without stop/reuse guard; the full lifecycle therefore is not qualified."}


def test_e08() -> dict[str, object]:
    control, repo, run_id = fresh("E08")
    seed_run(control, repo, run_id)
    observations: list[object] = []
    cycle_tickets = [{"id": "T-A", "goal_ref": "G-A", "criterion_refs": ["C-1"], "dependency_refs": ["T-B"], "state": "READY", "complexity": "bounded", "risk": "routine", "zone": []}, {"id": "T-B", "goal_ref": "G-B", "criterion_refs": ["C-1"], "dependency_refs": ["T-A"], "state": "READY", "complexity": "bounded", "risk": "routine", "zone": []}]
    cycle = copy.deepcopy(load_state(state_paths(control, run_id))[0]); cycle["tickets"] = cycle_tickets; cycle_path = RUN_ROOT / run_id / "cycle.json"; write_json(cycle_path, cycle)
    observations.append({"dependency_cycle": cmd([sys.executable, str(LEDGER), "validate", "--file", str(cycle_path), "--kind", "ledger"], expect=2)})
    # Nested worker checks are intentionally missing from the closed schema.
    bad_return = RUN_ROOT / run_id / "bad-return.json"; write_json(bad_return, {"identity": {"attempt_id": "A-1"}, "status": "DONE", "result": "ok", "files": [], "checks": [], "criteria": []})
    observations.append({"unknown_schema_nested_payload": cmd([sys.executable, str(LEDGER), "validate", "--file", str(bad_return), "--kind", "worker_return"])})
    observations.append({"missing_approved_doc": "prepare-handoff only validates the supplied projection; no state intent document hash/reference check is exposed"})
    observations.append({"symlink_return_rejection": "covered by inbox_file regular_non_symlink guard; see E04b fixture"})
    observations.append({"amendment_behavior": "cmd_amend stales tickets but does not validate dependent historical returns/reviews or their consumer closure"})

    # Targeted regression: a syntactically valid DONE return claims a path
    # outside the attempt's actual lease zone.
    control, repo, run_id = fresh("E08-write-set")
    seed_run(control, repo, run_id)
    packet_path = RUN_ROOT / run_id / "A-1-packet.json"
    write_json(packet_path, {"identity": {"run_id": run_id, "ticket_id": "T-1", "attempt_id": "A-1", "epoch": 0}, "kind": "worker", "mode": "implement", "goal": "write-set regression", "acceptance": [{"criterion_id": "C-1"}], "workspace": {"root": str(repo), "expected_base": None}, "write": {"allow": [{"path": "app.txt", "operations": ["modify"]}]}, "verification": [{"check_id": "oracle", "required": True}], "risk": {"level": "routine"}, "context": [{"ref": "contracts/worker.md"}], "return_target": {"path": "return.json"}})
    route_path = RUN_ROOT / run_id / "A-1-route.json"
    write_json(route_path, {"id": "route-A-1", "capability": "worker", "reasoning": "standard", "adequacy": "CONFIRMED", "context_grade": "PACKET_SCOPED"})
    dispatch_result = cmd([sys.executable, str(LEDGER), "dispatch", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-a", "--revision", "1", "--ticket-id", "T-1", "--attempt-id", "A-1", "--lease-id", "L-A-1", "--route-id", "route-A-1", "--packet", str(packet_path), "--route", str(route_path)])
    state, _ = load_state(state_paths(control, run_id))
    inbox = state_paths(control, run_id)["scratch"] / "A-1" / "return.json"
    write_json(inbox, {"identity": {"run_id": run_id, "ticket_id": "T-1", "attempt_id": "A-1", "packet_hash": state["attempts"][0]["packet_hash"], "epoch": 0}, "status": "DONE", "result": "claimed out-of-zone path", "files": [{"path": "other.txt", "operation": "modify"}], "checks": [{"check_id": "oracle", "outcome": "pass", "actual": "ok", "evidence_ref": "ev-worker"}], "criteria": [{"criterion_id": "C-1", "outcome": "satisfied", "evidence_refs": ["ev-worker"]}]})
    ingest = cmd([sys.executable, str(LEDGER), "ingest-return", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-a", "--revision", "2", "--attempt-id", "A-1", "--return-file", str(inbox), "--kind", "worker"])
    state, _ = load_state(state_paths(control, run_id))
    if not ingest["matched_expected"] or json.loads(str(ingest["stdout"])).get("status") != "BLOCKED":
        raise AssertionError(f"E08 out-of-zone return was not blocked: {ingest}")
    if state["attempts"][0]["lease"]["state"] != "quarantined" or state["lifecycle"]["control"] != "BLOCKED" or not any(issue["type"] == "write_set_violation" for issue in state.get("issues", [])):
        raise AssertionError(f"E08 out-of-zone return did not persist quarantine/issue: {state}")
    observations.append({"out_of_zone_done_return": {"dispatch": dispatch_result, "ingest": ingest, "lease_state": state["attempts"][0]["lease"]["state"], "run_control": state["lifecycle"]["control"], "issue_types": [issue["type"] for issue in state.get("issues", [])]}})
    return {"experiment": "E08", "observations": observations, "probe_summary": "Cycle and top-level schema rejection work. The targeted DONE return claiming other.txt outside the app.txt lease is now ingested only as blocked evidence with a typed ownership issue and quarantined lease; no candidate path remains available."}


def test_e09() -> dict[str, object]:
    control, repo, run_id = fresh("E09")
    tickets = []
    for i in range(6):
        dep = [] if i < 2 else (["T-0"] if i < 4 else ["T-2"])
        tickets.append({"id": f"T-{i}", "goal_ref": f"G-{i}", "criterion_refs": ["C-1"], "dependency_refs": dep, "state": "READY" if not dep else "PLANNED", "complexity": "coupled" if i == 3 else "bounded", "risk": "elevated" if i == 3 else "routine", "zone": [{"path": f"app-{i}.txt", "operations": ["create"]}], "current_attempt": None, "replacement_refs": []})
    seed_run(control, repo, run_id, tickets=tickets)
    p = state_paths(control, run_id); before = p["ledger"].stat().st_size
    observations = [{"ticket_count": len(tickets), "dag_depth": 3, "initial_ledger_bytes": before}, {"usage_field_initial": load_state(p)[0].get("usage")}, {"brief": cmd([sys.executable, str(LEDGER), "brief", "--control-root", str(control), "--run-id", run_id])}, {"forced_compaction": "no production compaction/resume primitive is exposed; only brief/status reads exist"}, {"restart_without_chat": "no orchestrator runtime exists in package, so this arm is not executable"}]
    return {"experiment": "E09", "observations": observations, "probe_summary": "A disposable six-ticket DAG can be described, but current V1 has no orchestrator trace, compaction hook, usage publication, helper-call attribution, or restart protocol; economy/context qualification is blocked/unknown."}


TESTS = {"E01": test_e01, "E04b": test_e04b, "E05": test_e05, "E06": test_e06, "E07": test_e07, "E08": test_e08, "E09": test_e09}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=[*TESTS, "all"], default="all")
    args = parser.parse_args()
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    selected = list(TESTS) if args.only == "all" else [args.only]
    result = {"package": {"ledger": str(LEDGER), "ledger_sha256": digest(LEDGER.read_bytes()), "schema_sha256": digest((ROOT / "schemas/contracts.schema.json").read_bytes())}, "experiments": [TESTS[name]() for name in selected]}
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
