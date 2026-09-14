#!/usr/bin/env python3
"""Disposable E09 economy/context/restart qualification trace."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from v1_final_qualification import fresh, ledger, run, shell, write_json  # noqa: E402


def state_of(control: Path, run_id: str) -> dict[str, object]:
    return ledger.load_state(ledger.paths(control, run_id))[0]


def set_ready(control: Path, run_id: str, owner: str, ticket_id: str) -> int:
    state = state_of(control, run_id)
    def change(next_state: dict[str, object]) -> None:
        ticket = next(item for item in next_state["tickets"] if item["id"] == ticket_id)
        ticket["state"] = "READY"
    return ledger.transaction(ledger.paths(control, run_id), owner, int(state["revision"]), change)["revision"]


def make_packet(root: Path, run_id: str, ticket_id: str, attempt_id: str, repo: Path, base: str) -> tuple[Path, Path]:
    packet_path = root / f"{attempt_id}-packet.json"
    route_path = root / f"{attempt_id}-route.json"
    write_json(packet_path, {"identity": {"run_id": run_id, "ticket_id": ticket_id, "attempt_id": attempt_id, "epoch": 1}, "kind": "worker", "mode": "implement", "goal": f"qualification worker {ticket_id}", "acceptance": [{"criterion_id": "C-1"}], "workspace": {"root": str(repo), "expected_base": base}, "write": {"allow": [{"path": f"{ticket_id}.txt", "operations": ["create"]}]}, "verification": [{"check_id": "oracle", "required": True}], "risk": {"level": "routine"}, "context": [{"ref": "E09-frozen-design"}], "return_target": {"path": "return.json"}})
    write_json(route_path, {"id": f"route-{attempt_id}", "capability": "worker", "reasoning": "bounded E09 qualification", "adequacy": "CONFIRMED", "context_grade": "PACKET_SCOPED"})
    return packet_path, route_path


def process_ticket(root: Path, control: Path, repo: Path, run_id: str, owner: str, ticket_id: str, index: int) -> dict[str, object]:
    state = state_of(control, run_id)
    attempt_id = f"A-{ticket_id}"
    base = shell("git", "rev-parse", "HEAD", cwd=repo)["stdout"]
    packet_path, route_path = make_packet(root, run_id, ticket_id, attempt_id, repo, base)
    dispatch = run("dispatch", "--control-root", str(control), "--run-id", run_id, "--owner-token", owner, "--revision", str(state["revision"]), "--ticket-id", ticket_id, "--attempt-id", attempt_id, "--lease-id", f"L-{attempt_id}", "--route-id", f"route-{attempt_id}", "--packet", str(packet_path), "--route", str(route_path))
    assert dispatch["matched_expected"], dispatch
    state = state_of(control, run_id)
    attempt = next(item for item in state["attempts"] if item["id"] == attempt_id)
    inbox = ledger.paths(control, run_id)["scratch"] / attempt_id / "return.json"
    write_json(inbox, {"identity": {"run_id": run_id, "ticket_id": ticket_id, "attempt_id": attempt_id, "packet_hash": attempt["packet_hash"], "epoch": 1}, "status": "DONE", "result": "qualification artifact", "files": [{"path": f"{ticket_id}.txt", "operation": "create"}], "checks": [{"check_id": "oracle", "outcome": "pass", "actual": "fixture", "evidence_ref": f"EV-{ticket_id}"}], "criteria": [{"criterion_id": "C-1", "outcome": "satisfied", "evidence_refs": [f"EV-{ticket_id}"]}]})
    ingest = run("ingest-return", "--control-root", str(control), "--run-id", run_id, "--owner-token", owner, "--revision", str(state["revision"]), "--attempt-id", attempt_id, "--return-file", str(inbox), "--kind", "worker")
    assert ingest["matched_expected"], ingest
    state = state_of(control, run_id)
    prepare = run("prepare-effect", "--control-root", str(control), "--run-id", run_id, "--owner-token", owner, "--revision", str(state["revision"]), "--operation-id", f"OP-{ticket_id}", "--kind", "candidate_commit", "--target", str(repo), "--expected-before", base, "--authority-ref", "E09")
    assert prepare["matched_expected"], prepare
    target = repo / f"{ticket_id}.txt"
    target.write_text(f"E09 artifact {ticket_id}\n", encoding="utf-8")
    shell("git", "add", target.name, cwd=repo)
    shell("git", "-c", "user.name=Qualification", "-c", "user.email=qualification@example.invalid", "commit", "-qm", f"E09 {ticket_id}", cwd=repo)
    commit_sha = shell("git", "rev-parse", "HEAD", cwd=repo)["stdout"]
    tree_sha = shell("git", "rev-parse", "HEAD^{tree}", cwd=repo)["stdout"]
    receipt = root / f"{attempt_id}-commit.json"
    write_json(receipt, {"status": "PASS", "checkout": str(repo), "base_sha": base, "commit_sha": commit_sha, "tree_sha": tree_sha, "authority_ref": "E09", "receipt_ref": f"E09-{ticket_id}"})
    state = state_of(control, run_id)
    candidate = run("candidate", "--control-root", str(control), "--run-id", run_id, "--owner-token", owner, "--revision", str(state["revision"]), "--attempt-id", attempt_id, "--commit-receipt", str(receipt), "--operation-id", f"OP-{ticket_id}")
    assert candidate["matched_expected"], candidate
    state, raw = ledger.load_state(ledger.paths(control, run_id))
    review_attempt = f"R-{ticket_id}"
    review_packet = root / f"{review_attempt}-packet.json"
    write_json(review_packet, {"identity": {"run_id": run_id, "attempt_id": review_attempt, "epoch": 1, "intent_revision": "v1"}, "kind": "review", "mandate": "independent E09 review", "subject_fingerprint": commit_sha, "criteria": [{"criterion_id": "C-1"}], "axes": ["correctness", "context"], "return_target": {"path": "review-return.json"}})
    review_prepared = run("prepare-review", "--control-root", str(control), "--run-id", run_id, "--owner-token", owner, "--revision", str(state["revision"]), "--ticket-id", ticket_id, "--review-attempt-id", review_attempt, "--lease-id", f"RL-{ticket_id}", "--packet", str(review_packet))
    assert review_prepared["matched_expected"], review_prepared
    state, raw = ledger.load_state(ledger.paths(control, run_id))
    review_file = ledger.paths(control, run_id)["scratch"] / review_attempt / "review-return.json"
    review_record = next(item for item in state["attempts"] if item["id"] == review_attempt)
    write_json(review_file, {"identity": {"run_id": run_id, "attempt_id": review_attempt, "packet_hash": review_record["packet_hash"], "epoch": 1}, "subject_fingerprint": commit_sha, "verdict": "PASS", "coverage": [{"criterion_id": "C-1", "outcome": "fulfilled", "evidence_refs": [f"EV-{ticket_id}"]}], "checks": [{"check_id": "correctness", "axis": "correctness", "outcome": "fulfilled", "actual": "fixture", "evidence_ref": f"EV-{ticket_id}"}, {"check_id": "context", "axis": "context", "outcome": "fulfilled", "actual": "fresh qualification context", "evidence_ref": "E09-frozen-design"}], "context_refs": ["E09-frozen-design"], "findings": []})
    integrity = root / f"{review_attempt}-integrity.json"
    write_json(integrity, {"status": "PASS", "candidate_fingerprint": commit_sha, "ledger_hash": ledger.sha256_bytes(raw)})
    state = state_of(control, run_id)
    integrated = run("integrate", "--control-root", str(control), "--run-id", run_id, "--owner-token", owner, "--revision", str(state["revision"]), "--attempt-id", review_attempt, "--review-file", str(review_file), "--integrity-receipt", str(integrity), "--review-id", f"REV-{ticket_id}")
    assert integrated["matched_expected"], integrated
    final = state_of(control, run_id)
    worker_lease = next(item for item in final["attempts"] if item["id"] == attempt_id)["lease"]["state"]
    return {"ticket": ticket_id, "index": index, "dispatch": dispatch, "ingest": ingest, "candidate": candidate, "review": review_prepared, "integrate": integrated, "worker_lease_after_integrate": worker_lease, "revision": final["revision"], "usage": final["usage"]}


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="codex-autopilot-e09-") as directory:
        root = Path(directory)
        control, repo, run_id = fresh(root, "E09", phase="EXECUTE")
        shell("git", "init", "-q", cwd=repo)
        (repo / "README.md").write_text("E09 disposable workspace\n", encoding="utf-8")
        shell("git", "add", "README.md", cwd=repo)
        shell("git", "-c", "user.name=Qualification", "-c", "user.email=qualification@example.invalid", "commit", "-qm", "E09 base", cwd=repo)
        state = state_of(control, run_id)
        ids = [f"E09-T{i:02d}" for i in range(1, 7)]
        dependencies = {ids[0]: [], ids[1]: [], ids[2]: [ids[0]], ids[3]: [ids[0]], ids[4]: [ids[2]], ids[5]: [ids[3]]}
        zones = {ids[0]: "routine", ids[1]: "routine", ids[2]: "coupled", ids[3]: "risk-seam", ids[4]: "amendment-target", ids[5]: "repair-target"}
        state["tickets"] = [{"id": ticket, "goal_ref": f"G-{ticket}", "criterion_refs": ["C-1"], "contract_refs": ["K-1"], "dependency_refs": dependencies[ticket], "state": "READY" if not dependencies[ticket] else "PLANNED", "verification_ref": "deterministic-oracle", "complexity": "coupled" if zones[ticket] in {"coupled", "risk-seam"} else "bounded", "risk": "elevated" if zones[ticket] in {"risk-seam", "repair-target"} else "routine", "zone": [{"path": f"{ticket}.txt", "operations": ["create"]}], "current_attempt": None, "replacement_refs": []} for ticket in ids]
        state["repository"]["initial_head"] = shell("git", "rev-parse", "HEAD", cwd=repo)["stdout"]
        ledger.validate_ledger(state)
        ledger.atomic_write(ledger.paths(control, run_id)["ledger"], ledger.canonical_bytes(state))
        initial_ledger_bytes = ledger.paths(control, run_id)["ledger"].stat().st_size

        takeover = run("recover", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-a", "--revision", "1", "--takeover", "--new-owner-token", "owner-b", "--attestation-ref", "E09-fresh-runtime")
        active = run("gate", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-b", "--revision", "2", "--phase", "EXECUTE", "--control", "ACTIVE", "--next-action", "E09-reground")
        if not takeover["matched_expected"] or not active["matched_expected"]:
            print(json.dumps({"qualified": False, "verdict": "V1 RELEASE BLOCKED", "blocker": "restart/takeover leg failed", "takeover": takeover, "active": active}, indent=2, sort_keys=True))
            return 2

        owner = "owner-b"
        processed: list[dict[str, object]] = []
        for index, ticket in enumerate(ids, 1):
            if dependencies[ticket]:
                current = state_of(control, run_id)
                assert all(next(item for item in current["tickets"] if item["id"] == dep)["state"] == "INTEGRATED" for dep in dependencies[ticket])
                set_ready(control, run_id, owner, ticket)
            result = process_ticket(root, control, repo, run_id, owner, ticket, index)
            processed.append(result)
            if result["worker_lease_after_integrate"] != "released":
                print(json.dumps({"qualified": False, "verdict": "V1 RELEASE BLOCKED", "blocker": {"code": "E09-LEASE-CLOSURE", "ticket": ticket, "observed": f"worker attempt A-{ticket} lease remains {result['worker_lease_after_integrate']} after INTEGRATED", "required": "all execution leases released at integrated/accepted boundary"}, "initial_ledger_bytes": initial_ledger_bytes, "ticket_count": len(ids), "dag_depth": 3, "processed": processed, "restart": {"takeover": takeover, "active": active}, "metrics": {"ledger_usage": result["usage"], "brief": "brief/status available; bytes recorded by current helper", "compaction": "forced compaction control unavailable on current supported Codex runtime", "platform_capability": "not treated as implementation defect"}}, indent=2, sort_keys=True))
                return 2

        final = state_of(control, run_id)
        brief = run("brief", "--control-root", str(control), "--run-id", run_id)
        print(json.dumps({"qualified": True, "verdict": "E09 PASS", "ticket_count": len(ids), "dag_depth": 3, "processed": processed, "restart": {"takeover": takeover, "active": active}, "metrics": {"ledger_usage": final["usage"], "brief": brief, "compaction": "forced compaction control unavailable on current supported Codex runtime; restart/re-grounding recorded", "platform_capability": "not treated as implementation defect"}}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
