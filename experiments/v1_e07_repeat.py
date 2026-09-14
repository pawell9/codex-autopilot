#!/usr/bin/env python3
"""Repeat only the E07 current-surface lifecycle qualification."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from v1_final_qualification import fresh, ledger, run, shell, write_json  # noqa: E402


def manual_microproject(root: Path, name: str, output: str, verdict: str) -> dict[str, object]:
    control, repo, run_id = fresh(root, name, phase="EXECUTE")
    (repo / "records.csv").write_text("ok\nmalformed\nedge\n", encoding="utf-8")
    (repo / "app.py").write_text(f"print('{output}')\n", encoding="utf-8")
    shell("git", "init", "-q", cwd=repo)
    shell("git", "add", "records.csv", "app.py", cwd=repo)
    shell("git", "-c", "user.name=Qualification", "-c", "user.email=qualification@example.invalid", "commit", "-qm", "base", cwd=repo)
    base = shell("git", "rev-parse", "HEAD", cwd=repo)["stdout"]
    packet = root / f"{name}-worker.json"
    write_json(packet, {"identity": {"run_id": run_id, "ticket_id": "T-1", "attempt_id": "A-1", "epoch": 0}, "kind": "worker", "mode": "implement", "goal": "filter fixture records", "acceptance": [{"criterion_id": "C-1"}], "workspace": {"root": str(repo), "expected_base": base}, "write": {"allow": [{"path": "app.py", "operations": ["modify"]}]}, "verification": [{"check_id": "oracle", "required": True}], "risk": {"level": "routine"}, "context": [{"ref": "contracts/worker.md"}], "return_target": {"path": "return.json"}})
    route = root / f"{name}-route.json"
    write_json(route, {"id": "route-A-1", "capability": "worker", "reasoning": "bounded micro-project", "adequacy": "CONFIRMED", "context_grade": "PACKET_SCOPED"})
    state, _ = ledger.load_state(ledger.paths(control, run_id))
    dispatch = run("dispatch", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-a", "--revision", str(state["revision"]), "--ticket-id", "T-1", "--attempt-id", "A-1", "--lease-id", "L-1", "--route-id", "route-A-1", "--packet", str(packet), "--route", str(route))
    state, _ = ledger.load_state(ledger.paths(control, run_id)); attempt = state["attempts"][0]; inbox = ledger.paths(control, run_id)["scratch"] / "A-1" / "return.json"
    write_json(inbox, {"identity": {"run_id": run_id, "ticket_id": "T-1", "attempt_id": "A-1", "packet_hash": attempt["packet_hash"], "epoch": 0}, "status": "DONE", "result": "implemented", "files": [{"path": "app.py", "operation": "modify"}], "checks": [{"check_id": "oracle", "outcome": "pass", "actual": "fixture", "evidence_ref": "EV-worker"}], "criteria": [{"criterion_id": "C-1", "outcome": "satisfied", "evidence_refs": ["EV-worker"]}]})
    ingest = run("ingest-return", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-a", "--revision", str(state["revision"]), "--attempt-id", "A-1", "--return-file", str(inbox), "--kind", "worker")
    state, _ = ledger.load_state(ledger.paths(control, run_id))
    prepare = run("prepare-effect", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-a", "--revision", str(state["revision"]), "--operation-id", "OP-1", "--kind", "candidate_commit", "--target", str(repo), "--expected-before", base, "--authority-ref", "E07")
    shell("git", "add", "app.py", cwd=repo); shell("git", "-c", "user.name=Qualification", "-c", "user.email=qualification@example.invalid", "commit", "-qm", "candidate", cwd=repo)
    candidate_sha = shell("git", "rev-parse", "HEAD", cwd=repo)["stdout"]; tree_sha = shell("git", "rev-parse", "HEAD^{tree}", cwd=repo)["stdout"]
    receipt = root / f"{name}-commit.json"; write_json(receipt, {"status": "PASS", "checkout": str(repo), "base_sha": base, "commit_sha": candidate_sha, "tree_sha": tree_sha, "authority_ref": "E07", "receipt_ref": "E07-commit"})
    state, _ = ledger.load_state(ledger.paths(control, run_id)); candidate = run("candidate", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-a", "--revision", str(state["revision"]), "--attempt-id", "A-1", "--commit-receipt", str(receipt), "--operation-id", "OP-1")
    state, raw = ledger.load_state(ledger.paths(control, run_id)); export = root / f"{name}-export"; bundle = root / f"{name}-bundle"; export.mkdir(); shutil.copy2(repo / "app.py", export / "app.py")
    state, _ = ledger.load_state(ledger.paths(control, run_id))
    review_packet_path = root / f"{name}-review-packet.json"
    write_json(review_packet_path, {"identity": {"run_id": run_id, "attempt_id": "A-review", "epoch": 0, "intent_revision": "v1"}, "kind": "review", "mandate": "prepare independent current-intent G5 handoff", "subject_fingerprint": candidate_sha, "criteria": [{"criterion_id": "C-1"}], "axes": ["current-intent"], "return_target": {"path": "review-return.json"}})
    review_prepared = run("prepare-review", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-a", "--revision", str(state["revision"]), "--ticket-id", "T-1", "--review-attempt-id", "A-review", "--lease-id", "RL-1", "--packet", str(review_packet_path))
    state, _ = ledger.load_state(ledger.paths(control, run_id))
    packet_path = root / f"{name}-g5-packet.json"; projection_path = root / f"{name}-projection.json"
    write_json(packet_path, {"identity": {"run_id": run_id, "attempt_id": "A-review", "epoch": 0, "intent_revision": "v1"}, "kind": "acceptance", "mandate": "independent current-intent G5", "subject_fingerprint": candidate_sha, "criteria": [{"id": "C-1", "oracle": "record count"}], "axes": ["current-intent", "independent-oracle"], "constraints": ["pristine export only"], "subject": {"candidate_sha": candidate_sha, "candidate_tree_sha": tree_sha, "export_label": "candidate-export", "pristine_check_required": True}, "return_target": {"path": "acceptance-return.json", "exact_json_only": True}})
    write_json(projection_path, {"kind": "acceptance_projection", "intent_revision": "v1", "candidate_fingerprint": candidate_sha, "goal": "filter records", "criteria": [{"id": "C-1", "oracle": "expected valid records count is 2", "pass_condition": "independent export check"}], "exclusions": [], "return_schema": "acceptance_return"})
    handoff = run("prepare-handoff", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-a", "--revision", str(state["revision"]), "--attempt-id", "A-review", "--packet", str(packet_path), "--projection", str(projection_path), "--export-root", str(export), "--bundle-root", str(bundle))
    state, raw = ledger.load_state(ledger.paths(control, run_id)); attempt = next(item for item in state["attempts"] if item["id"] == "A-review"); manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8")); manifest_hash = ledger.sha256_file(bundle / "manifest.json")
    env = root / f"{name}-environment.json"; context = root / f"{name}-context.json"; integrity = root / f"{name}-integrity.json"; ret = ledger.paths(control, run_id)["scratch"] / "A-review" / "acceptance-return.json"
    write_json(env, {"receipt_id": f"env-{name}", "status": "PASS", "topology": {"surface": "disposable-review-root"}, "inventory_hashes": [{"path": "candidate-export/app.py", "sha256": ledger.sha256_file(export / "app.py")}], "effective_grants": {"authoritative_repo": False}, "boundary_probes": [{"probe": "authoritative-input", "result": "absent"}], "authoritative_absent": True})
    write_json(context, {"receipt_id": f"ctx-{name}", "status": "PASS", "grade": "MANUAL_ATTESTED_CLEAN", "packet_hash": attempt["packet_hash"], "export_hash": manifest_hash, "clean_input": True, "contamination_absent": True, "session_provenance": {"session": "new-disposable-review-process"}})
    outcome = "fulfilled" if verdict == "PASS" else "partial"
    write_json(ret, {"identity": {"run_id": run_id, "attempt_id": "A-review", "packet_hash": attempt["packet_hash"], "intent_revision": "v1", "epoch": 0}, "candidate_fingerprint": candidate_sha, "verdict": verdict, "outcomes": [{"criterion_id": "C-1", "outcome": outcome, "evidence_refs": [f"EV-{name}"]}], "checks": [{"check_id": "independent-record-oracle", "outcome": "fulfilled" if verdict == "PASS" else "failed", "actual": f"app output={output}; records expected=2", "evidence_ref": f"EV-{name}"}], "findings": []})
    write_json(integrity, {"status": "PASS", "candidate_fingerprint": candidate_sha, "ledger_hash": ledger.sha256_bytes(raw)})
    state, _ = ledger.load_state(ledger.paths(control, run_id)); imported = run("import-manual", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-a", "--revision", str(state["revision"]), "--attempt-id", "A-review", "--return-file", str(ret), "--environment-receipt", str(env), "--context-receipt", str(context), "--integrity-receipt", str(integrity), "--intent-revision", "v1", "--candidate-fingerprint", candidate_sha, "--required-criteria", "C-1")
    final, _ = ledger.load_state(ledger.paths(control, run_id))
    g6 = None
    if verdict == "PASS":
        g6 = run("gate", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-a", "--revision", str(final["revision"]), "--phase", "ACCEPT", "--control", "ACCEPTED", "--next-action", "e07-terminal")
        final, _ = ledger.load_state(ledger.paths(control, run_id))
    expected_control = "ACCEPTED" if verdict == "PASS" else "BLOCKED"
    return {"dispatch": dispatch, "ingest": ingest, "prepare": prepare, "candidate": candidate, "review_prepared": review_prepared, "handoff": handoff, "import": imported, "g6": g6, "final_control": final["lifecycle"]["control"], "expected_control": expected_control, "qualified": all([dispatch["matched_expected"], ingest["matched_expected"], prepare["matched_expected"], candidate["matched_expected"], review_prepared["matched_expected"], handoff["matched_expected"], imported["matched_expected"], final["lifecycle"]["control"] == expected_control, g6 is None or g6["matched_expected"]])}


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="codex-autopilot-e07-repeat-") as directory:
        root = Path(directory); observations: list[dict[str, object]] = []
        control, repo, run_id = fresh(root, "E07-pause", phase="EXECUTE")
        direct = run("gate", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-a", "--revision", "str(1)", "--control", "PAUSED", expect=2)
        quiesce = run("gate", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-a", "--revision", "1", "--control", "QUIESCING")
        paused = run("gate", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-a", "--revision", "2", "--control", "PAUSED")
        recovered = run("recover", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-a", "--revision", "3", "--takeover", "--new-owner-token", "owner-b", "--attestation-ref", "E07")
        resumed = run("gate", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-b", "--revision", "4", "--control", "ACTIVE", "--next-action", "e07-resumed")
        state, _ = ledger.load_state(ledger.paths(control, run_id))
        observations.append({"pause_resume": {"direct_pause": direct, "quiesce": quiesce, "paused": paused, "recover": recovered, "resume": resumed, "final_control": state["lifecycle"]["control"]}, "qualified": direct["matched_expected"] and quiesce["matched_expected"] and paused["matched_expected"] and recovered["matched_expected"] and resumed["matched_expected"] and state["lifecycle"]["control"] == "ACTIVE"})
        normal = manual_microproject(root, "E07-normal", "2", "PASS")
        broken = manual_microproject(root, "E07-broken", "1", "BLOCK")
        observations.append({"normal_microproject_g0_g6": normal, "qualified": normal["qualified"]})
        observations.append({"green_but_broken_oracle": broken, "qualified": broken["qualified"]})
        cancel_control, cancel_repo, cancel_run = fresh(root, "E07-cancel", phase="EXECUTE"); foreign = cancel_repo / "foreign.txt"; foreign.write_text("preserve\n", encoding="utf-8")
        q = run("cancel", "--control-root", str(cancel_control), "--run-id", cancel_run, "--owner-token", "owner-a", "--revision", "1")
        stop = root / "E07-stop.json"; write_json(stop, {"status": "PASS", "writers_stopped": True, "reconciled": True}); state, _ = ledger.load_state(ledger.paths(cancel_control, cancel_run)); c = run("cancel", "--control-root", str(cancel_control), "--run-id", cancel_run, "--owner-token", "owner-a", "--revision", str(state["revision"]), "--finalize", "--stop-evidence", str(stop)); state, _ = ledger.load_state(ledger.paths(cancel_control, cancel_run))
        observations.append({"cancel": {"request": q, "finalize": c, "control": state["lifecycle"]["control"], "foreign_preserved": foreign.read_text(encoding="utf-8") == "preserve\n"}, "qualified": q["matched_expected"] and c["matched_expected"] and state["lifecycle"]["control"] == "CANCELLED" and foreign.exists()})
        amend_control, amend_repo, amend_run = fresh(root, "E07-amend", phase="EXECUTE"); intent_v2 = root / "E07-intent-v2.md"; intent_v2.write_text("# amended intent\n\nMalformed rows are rejected.\n", encoding="utf-8"); amended = run("amend", "--control-root", str(amend_control), "--run-id", amend_run, "--owner-token", "owner-a", "--revision", "1", "--intent-file", str(intent_v2), "--doc-id", "D-2", "--doc-version", "v2", "--intent-revision", "v2", "--amendment-id", "AM-E07", "--authority-ref", "E07-user-authority"); amended_state, _ = ledger.load_state(ledger.paths(amend_control, amend_run))
        observations.append({"amendment": {"result": amended, "phase": amended_state["lifecycle"]["phase"], "ticket_state": amended_state["tickets"][0]["state"], "invalidation": amended_state["invalidations"][0]}, "qualified": amended["matched_expected"] and amended_state["lifecycle"]["phase"] == "INTENT" and amended_state["tickets"][0]["state"] == "STALE"})
        print(json.dumps({"experiment": "E07", "observations": observations, "qualified": all(item["qualified"] for item in observations)}, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
