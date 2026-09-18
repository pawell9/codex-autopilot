#!/usr/bin/env python3
"""Synthetic 40-ticket lifecycle qualification for the V1 ledger.

This exercises bookkeeping and lifecycle helpers without starting agents.  It
uses a disposable real Git repository so every synthetic candidate carries the
same base/tree/write-set proof required from an ordinary production candidate.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import dashboard  # noqa: E402
import ledger  # noqa: E402


CLI = [sys.executable, str(ROOT / "tools" / "ledger.py")]


def write_json(path: Path, value: object) -> None:
    ledger.atomic_write(path, ledger.canonical_bytes(value))


def cli(*args: str, expect: int = 0) -> dict[str, object]:
    result = subprocess.run([*CLI, *args], text=True, capture_output=True)
    if result.returncode != expect:
        raise AssertionError(f"expected {expect}, got {result.returncode}: {result.stdout}\n{result.stderr}")
    output = result.stdout.strip() or result.stderr.strip()
    return json.loads(output) if output else {}


def ticket_id(index: int) -> str:
    return f"ticket-{index:02d}"


def build_tickets(count: int) -> list[dict[str, object]]:
    tickets: list[dict[str, object]] = []
    for index in range(count):
        dependencies = []
        if index >= 1:
            dependencies.append(ticket_id(index - 1))
        if index >= 3 and index % 4 == 0:
            dependencies.append(ticket_id(index - 3))
        if index >= 5 and index % 5 == 0:
            dependencies.append(ticket_id(index - 5))
        tickets.append({
            "id": ticket_id(index),
            "goal_ref": "qualification-goal",
            "criterion_refs": ["C-qualification"],
            "contract_refs": ["K-qualification"],
            "dependency_refs": dependencies,
            "state": "READY" if index == 0 else "PLANNED",
            "verification_ref": "synthetic-oracle",
            "complexity": "coupled" if index % 7 == 0 else "bounded",
            "risk": "elevated" if index % 11 == 0 else "routine",
            "zone": [{"path": f"fixture/{ticket_id(index)}.txt", "operations": ["modify"]}],
            "current_attempt": None,
            "replacement_refs": [],
        })
    return tickets


def write_ticket_artifact(run_root: Path, ticket: dict[str, object]) -> None:
    artifact = run_root / "docs" / "tickets" / f"{ticket['id']}.md"
    dependencies = ",".join(ticket.get("dependency_refs", [])) or "none"
    content = f"# {ticket['id']}\n\nid: {ticket['id']}\nstate: {ticket['state']}\ndependencies: {dependencies}\n"
    ledger.atomic_write(artifact, content.encode("utf-8"))


def assert_artifacts_match(run_root: Path, tickets: list[dict[str, object]]) -> None:
    for ticket in tickets:
        artifact = run_root / "docs" / "tickets" / f"{ticket['id']}.md"
        text = artifact.read_text(encoding="utf-8")
        if f"id: {ticket['id']}" not in text or f"state: {ticket['state']}" not in text:
            raise AssertionError(f"canonical ticket artifact drift: {ticket['id']}")


def worker_identity(state: dict[str, object], ticket: dict[str, object], attempt_id: str) -> dict[str, object]:
    intent = ledger.current_intent_binding(state)
    publication = state["design_publication"]
    return {
        "run_id": state["run_id"], "ticket_id": ticket["id"], "attempt_id": attempt_id,
        "epoch": state["owner"]["epoch"], "intent_revision": intent["revision"],
        "intent_document_ref": intent["document_ref"], "intent_document_hash": intent["document_hash"],
        "design_publication_ref": publication["id"],
        "design_publication_hash": publication["publication_hash"],
        "design_publication_revision": publication["published_revision"],
        "contract_refs": sorted(ticket.get("contract_refs", [])),
    }


def worker_packet(run_id: str, ticket: dict[str, object], attempt_id: str, mode: str = "implement", repair: dict[str, str] | None = None, *, state: dict[str, object]) -> dict[str, object]:
    identity = worker_identity(state, ticket, attempt_id)
    packet: dict[str, object] = {
        "identity": identity,
        "intent_revision": identity["intent_revision"],
        "intent_document_ref": identity["intent_document_ref"],
        "intent_document_hash": identity["intent_document_hash"],
        "kind": "worker", "mode": mode, "goal": "synthetic qualification worker",
        "acceptance": [{"criterion_id": "C-qualification"}],
        "workspace": {"root": "", "expected_base": None},
        "write": {"allow": [{"path": f"fixture/{ticket['id']}.txt", "operations": ["modify"]}]},
        "verification": [{"check_id": "synthetic-oracle", "required": True}],
        "risk": {"level": ticket["risk"]}, "context": [{"ref": "contracts/worker.md"}],
        "return_target": {"path": "return.json"},
    }
    if repair is not None:
        packet["repair"] = repair
    return packet


def review_packet(run_id: str, ticket: dict[str, object], attempt_id: str, candidate_sha: str) -> dict[str, object]:
    return {
        "identity": {"run_id": run_id, "ticket_id": ticket["id"], "attempt_id": attempt_id, "epoch": 0},
        "kind": "review", "mandate": "synthetic independent change review", "subject_fingerprint": candidate_sha,
        "criteria": [{"criterion_id": "C-qualification"}], "axes": ["correctness"],
        "return_target": {"path": "review-return.json"},
    }


def mark_ready(control: Path, run_id: str, ticket: dict[str, object], token: str, revision: int) -> dict[str, object]:
    paths = ledger.paths(control, run_id)

    def change(state: dict[str, object]) -> None:
        current = next(item for item in state["tickets"] if item["id"] == ticket["id"])
        if current["state"] != "PLANNED":
            return
        if any(next(item for item in state["tickets"] if item["id"] == dep)["state"] != "INTEGRATED" for dep in current["dependency_refs"]):
            raise ledger.LedgerError("fixture attempted READY before dependencies were INTEGRATED")
        current["state"] = "READY"

    result = ledger.transaction(paths, token, revision, change)
    return result


def process_ticket(control: Path, repo: Path, run_id: str, ticket: dict[str, object], root: Path, repair: bool = False, repair_authority_ref: str | None = None) -> tuple[bool, int]:
    paths = ledger.paths(control, run_id)
    state, _ = ledger.load_state(paths)
    index = int(str(ticket["id"]).rsplit("-", 1)[1])
    attempt_id = f"attempt-{index:02d}" + ("-repair" if repair else "")
    repair_contract = ticket.get("repair") if repair else None
    base_sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, text=True, capture_output=True,
    ).stdout.strip()
    packet_path = root / f"{attempt_id}.packet.json"
    route_path = root / f"{attempt_id}.route.json"
    packet = worker_packet(run_id, ticket, attempt_id, "repair" if repair else "implement", repair_contract, state=state)
    packet_identity = packet["identity"]
    # The BLOCKED repair candidate commit must bind to the worker's actual
    # checkout and base, not a fixture-only authority string.
    packet["workspace"] = {"root": str(repo), "expected_base": base_sha}
    write_json(packet_path, packet)
    write_json(route_path, {"id": f"route-{attempt_id}", "capability": "fixture-worker", "reasoning": "synthetic", "requested_binding": "fixture-model", "observed_binding": "fixture-model", "adequacy": "CONFIRMED", "context_grade": "PACKET_SCOPED"})
    cli("dispatch", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner", "--revision", str(state["revision"]), "--ticket-id", str(ticket["id"]), "--attempt-id", attempt_id, "--lease-id", f"lease-{attempt_id}", "--route-id", f"route-{attempt_id}", "--packet", str(packet_path), "--route", str(route_path))
    state, _ = ledger.load_state(paths)
    attempt = next(item for item in state["attempts"] if item["id"] == attempt_id)
    inbox = paths["scratch"] / attempt_id / "return.json"
    relative_path = f"fixture/{ticket['id']}.txt"
    (repo / relative_path).write_text(
        f"candidate from {attempt_id}\n", encoding="utf-8",
    )
    payload = {"identity": {**packet_identity, "packet_hash": attempt["packet_hash"]}, "status": "DONE", "result": "synthetic completed worker", "files": [{"path": relative_path, "operation": "modify"}], "checks": [{"check_id": "synthetic-oracle", "outcome": "pass", "actual": "fixture", "evidence_ref": "ev-worker"}], "criteria": [{"criterion_id": "C-qualification", "outcome": "satisfied", "evidence_refs": ["ev-worker"]}]}
    write_json(inbox, payload)
    cli("ingest-return", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner", "--revision", str(state["revision"]), "--attempt-id", attempt_id, "--return-file", str(inbox), "--kind", "worker")
    state, _ = ledger.load_state(paths)
    operation_id = f"operation-{index:02d}" + ("-repair" if repair else "")
    authority_ref = repair_authority_ref if repair and repair_authority_ref else "qualification"
    cli("prepare-effect", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner", "--revision", str(state["revision"]), "--operation-id", operation_id, "--kind", "candidate_commit", "--target", str(repo), "--expected-before", base_sha, "--authority-ref", authority_ref)
    subprocess.run(["git", "-C", str(repo), "add", "--", relative_path], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=Qualification", "-c", "user.email=qualification@example.invalid", "commit", "-qm", f"candidate {attempt_id}"],
        check=True,
    )
    candidate_sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, text=True, capture_output=True,
    ).stdout.strip()
    tree_sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD^{tree}"], check=True, text=True, capture_output=True,
    ).stdout.strip()
    receipt = root / f"{operation_id}.receipt.json"
    write_json(receipt, {"status": "PASS", "run_id": run_id, "ticket_id": ticket["id"], "attempt_id": attempt_id, "operation_id": operation_id, "kind": "candidate_commit", "target": str(repo), "checkout": str(repo), "expected_before": base_sha, "base_sha": base_sha, "intended_after": candidate_sha, "commit_sha": candidate_sha, "tree_sha": tree_sha, "authority_ref": authority_ref, "receipt_ref": operation_id})
    state, _ = ledger.load_state(paths)
    cli("candidate", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner", "--revision", str(state["revision"]), "--attempt-id", attempt_id, "--commit-receipt", str(receipt), "--operation-id", operation_id)
    state, _ = ledger.load_state(paths)
    review_attempt_id = f"review-{index:02d}" + ("-repair" if repair else "")
    review_file = root / f"{review_attempt_id}.packet.json"
    write_json(review_file, review_packet(run_id, ticket, review_attempt_id, candidate_sha))
    cli("prepare-review", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner", "--revision", str(state["revision"]), "--ticket-id", str(ticket["id"]), "--review-attempt-id", review_attempt_id, "--lease-id", f"lease-{review_attempt_id}", "--packet", str(review_file))
    state, raw = ledger.load_state(paths)
    review_attempt = next(item for item in state["attempts"] if item["id"] == review_attempt_id)
    review_return = paths["scratch"] / review_attempt_id / "return.json"
    should_block_for_repair = not repair and index == 0
    review_payload: dict[str, object] = {
        "identity": {"run_id": run_id, "ticket_id": ticket["id"], "attempt_id": review_attempt_id,
                     "packet_hash": review_attempt["packet_hash"], "epoch": 0},
        "subject_fingerprint": candidate_sha,
        "verdict": "BLOCK" if should_block_for_repair else "PASS",
        "coverage": [{"criterion_id": "C-qualification",
                      "outcome": "missing" if should_block_for_repair else "fulfilled",
                      "evidence_refs": ["ev-review"]}],
        "checks": [{"check_id": "correctness", "axis": "correctness",
                    "outcome": "failed" if should_block_for_repair else "fulfilled",
                    "actual": "seeded defect" if should_block_for_repair else "fixture",
                    "evidence_ref": "ev-review"}],
        "context_refs": ["synthetic-clean-review"],
        "findings": ([{"axis": "correctness", "impact": "blocking", "claim": "seeded candidate defect",
                       "expected": "correct", "actual": "defective", "evidence": "ev-review",
                       "affected_refs": [ticket["id"]]}] if should_block_for_repair else []),
    }
    if repair_contract:
        review_payload["finding_resolution"] = [{
            "finding_ref": repair_contract["finding_ref"], "candidate_ref": f"candidate-{attempt_id}",
            "evidence_refs": ["ev-review"],
            "reason": "The fresh PASS review verifies the exact repaired finding on the current candidate.",
        }]
    write_json(review_return, review_payload)
    if should_block_for_repair:
        cli("ingest-return", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner",
            "--revision", str(state["revision"]), "--attempt-id", review_attempt_id,
            "--return-file", str(review_return), "--kind", "review")
        return True, int(ledger.load_state(paths)[0]["revision"])
    integrity = root / f"{review_attempt_id}.integrity.json"
    write_json(integrity, {"status": "PASS", "candidate_fingerprint": candidate_sha, "ledger_hash": ledger.sha256_bytes(raw)})
    cli("integrate", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner", "--revision", str(state["revision"]), "--attempt-id", review_attempt_id, "--review-file", str(review_return), "--integrity-receipt", str(integrity), "--review-id", f"REV-{index:02d}" + ("-repair" if repair else ""))
    final, _ = ledger.load_state(paths)
    integrated = next(item for item in final["tickets"] if item["id"] == ticket["id"])
    if integrated["state"] != "INTEGRATED":
        raise AssertionError(f"ticket did not integrate: {ticket['id']}")
    return False, int(final["revision"])


def run_qualification() -> dict[str, object]:
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="codex-autopilot-40-ticket-") as directory:
        root = Path(directory)
        control, repo = root / "control", root / "repo"
        control.mkdir(); repo.mkdir()
        tickets = build_tickets(40)
        subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
        (repo / "fixture").mkdir()
        for ticket in tickets:
            (repo / "fixture" / f"{ticket['id']}.txt").write_text("baseline\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "fixture"], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "-c", "user.name=Qualification", "-c", "user.email=qualification@example.invalid", "commit", "-qm", "qualification baseline"],
            check=True,
        )
        run_id = "qualification-40"
        init = cli("init", "--control-root", str(control), "--repo-root", str(repo), "--run-id", run_id, "--owner-token", "owner", "--request", "codex-autopilot полный автомат, глубокая — сделай qualification")
        paths = ledger.paths(control, run_id)
        state, previous = ledger.load_state(paths)
        intent = paths["docs"] / "intent" / "v1.md"
        design = paths["docs"] / "design" / "v1.md"
        intent_bytes = b"# Synthetic 40-ticket qualification\n"
        ledger.atomic_write(intent, intent_bytes)
        design_bytes = b"# Synthetic 40-ticket design\n"
        ledger.atomic_write(design, design_bytes)
        for ticket in tickets:
            write_ticket_artifact(paths["run"], ticket)
        route_ids = ["route-premature"]
        route_ids.extend(f"route-attempt-{index:02d}" for index in range(len(tickets)))
        route_ids.extend(f"route-attempt-{index:02d}-repair" for index in range(len(tickets)))
        routes = [{"id": route_id, "capability": "fixture-worker", "reasoning": "synthetic", "requested_binding": "fixture-model", "observed_binding": "fixture-model", "adequacy": "CONFIRMED", "context_grade": "PACKET_SCOPED"} for route_id in route_ids]
        route_refs = [item["id"] for item in routes]
        bundle_raw = ledger.canonical_bytes({"fixture": "40-ticket-design-publication", "design_document_hash": ledger.sha256_bytes(design_bytes), "ticket_refs": [ticket["id"] for ticket in tickets], "criterion_refs": ["C-qualification"], "contract_refs": ["K-qualification"], "routes": routes})
        publication_hash = ledger.object_store(paths, bundle_raw)
        publication = {"id": "B-qualification", "version": "v1", "status": "PUBLISHED", "owner_epoch": 0, "intent_revision": "v1", "intent_document_ref": "D-qualification", "intent_document_hash": ledger.sha256_bytes(intent_bytes), "publication_hash": publication_hash, "bundle_ref": f"objects/{publication_hash}", "published_revision": 1, "document_refs": ["D-design-qualification"], "requirement_refs": ["R-qualification"], "criterion_refs": ["C-qualification"], "contract_refs": ["K-qualification"], "ticket_refs": [ticket["id"] for ticket in tickets], "route_refs": route_refs}
        design_reviews = [
            {"id": "REV-G2-qualification", "mandate": "synthetic coverage qualification", "subject_fingerprint": publication_hash, "verdict": "PASS", "return_ref": "objects/coverage-qualification", "context_refs": ["synthetic"], "finding_refs": [], "intent_revision": "v1", "review_kind": "coverage", "target_revision": 1},
            {"id": "REV-G3-qualification", "mandate": "synthetic plan qualification", "subject_fingerprint": publication_hash, "verdict": "PASS", "return_ref": "objects/plan-qualification", "context_refs": ["synthetic"], "finding_refs": [], "intent_revision": "v1", "review_kind": "plan", "target_revision": 1},
        ]
        state.update({"repository": {**state["repository"], "branch": "fixture", "initial_head": subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, text=True, capture_output=True).stdout.strip(), "checkout": str(repo)}, "documents": [{"id": "D-qualification", "version": "v1", "path": str(intent), "hash": ledger.sha256_bytes(intent_bytes), "kind": "intent", "section_anchors": []}, {"id": "D-design-qualification", "version": "v1", "path": str(design), "hash": ledger.sha256_bytes(design_bytes), "kind": "design", "section_anchors": []}], "intent": {"current_revision": "v1", "document_ref": "D-qualification", "document_hash": ledger.sha256_bytes(intent_bytes), "approved_amendments": []}, "requirements": [{"id": "R-qualification", "version": "v1", "status": "active", "provenance_refs": ["D-qualification"], "criterion_refs": ["C-qualification"]}], "criteria": [{"id": "C-qualification", "version": "v1", "requirement_refs": ["R-qualification"], "oracle": "synthetic lifecycle oracle", "status": "active", "source_ref": "D-qualification"}], "contracts": [{"id": "K-qualification", "version": "v1", "status": "active", "provenance_refs": ["D-qualification"], "producer_refs": [], "consumer_refs": [ticket["id"] for ticket in tickets], "implementation_availability": "available", "implementation_availability_evidence_refs": ["fixture:qualification-contract-available"]}], "tickets": tickets, "routes": routes, "design_publication": publication, "design_publication_history": [publication], "reviews": design_reviews, "lifecycle": {"phase": "EXECUTE", "control": "ACTIVE", "reason": "40_ticket_qualification", "issue_refs": [], "stop_target": None, "next_action": {"kind": "qualification", "subject_refs": [ticket["id"] for ticket in tickets], "preconditions": [], "read_refs": ["phases/execute.md"]}}})
        state["revision"] = 1
        state["previous_publication_hash"] = ledger.sha256_bytes(previous)
        ledger.validate_ledger(state)
        ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
        assert ledger.resolved_run_settings(state) == {"interaction_mode": "full", "depth": "deep"}

        # Explicitly prove the helper refuses premature readiness/dispatch.
        premature_ticket = tickets[1]
        premature_packet = root / "premature.packet.json"
        premature_route = root / "premature.route.json"
        write_json(premature_packet, worker_packet(run_id, premature_ticket, "premature-attempt", state=state))
        premature_route_record = next(item for item in routes if item["id"] == "route-premature")
        write_json(premature_route, premature_route_record)
        premature = cli("dispatch", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner", "--revision", "1", "--ticket-id", str(premature_ticket["id"]), "--attempt-id", "premature-attempt", "--lease-id", "premature-lease", "--route-id", "route-premature", "--packet", str(premature_packet), "--route", str(premature_route), expect=2)

        processed: list[str] = []
        repair_seen = False
        paused_seen = False
        recovery_seen = False
        while len(processed) < len(tickets):
            state, _ = ledger.load_state(paths)
            next_ticket = next(ticket for ticket in tickets if ticket["id"] not in processed and ticket["state"] == "PLANNED" and all(next(item for item in state["tickets"] if item["id"] == dep)["state"] == "INTEGRATED" for dep in ticket["dependency_refs"])) if any(ticket["id"] not in processed and ticket["state"] == "PLANNED" and all(next(item for item in state["tickets"] if item["id"] == dep)["state"] == "INTEGRATED" for dep in ticket["dependency_refs"]) for ticket in tickets) else next(ticket for ticket in tickets if ticket["id"] not in processed and ticket["state"] == "READY")
            if next_ticket["state"] == "PLANNED":
                state = mark_ready(control, run_id, next_ticket, "owner", int(state["revision"]))
                next_ticket["state"] = "READY"
            blocked, _ = process_ticket(control, repo, run_id, next_ticket, root)
            if blocked:
                repair_seen = True
                state, _ = ledger.load_state(paths)
                finding_id = next(item["id"] for item in state["findings"] if next_ticket["id"] in item.get("affected_refs", []))
                next_ticket["repair"] = {"cause": "implementation", "finding_ref": finding_id, "hypothesis": "synthetic first candidate is intentionally blocked", "expected_proof": "candidate-bound repair review passes", "stopping_condition": "one changed repair succeeds", "causal_change": "use repaired synthetic path"}
                repair_contract = root / "qualification-repair.json"
                write_json(repair_contract, next_ticket["repair"])
                cli("authorize-repair", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner", "--revision", str(state["revision"]), "--ticket-id", str(next_ticket["id"]), "--finding-ref", finding_id, "--authorization-id", "AUTH-qualification-repair", "--repair-contract", str(repair_contract))
                next_ticket["state"] = "READY"
                process_ticket(control, repo, run_id, next_ticket, root, repair=True, repair_authority_ref="AUTH-qualification-repair")
                state, _ = ledger.load_state(paths)
                if ledger.open_ticket_finding_obligations(state, str(next_ticket["id"])):
                    raise AssertionError(f"exact reviewed repair left the ticket obligation open: {ledger.open_ticket_finding_obligations(state, str(next_ticket['id']))}")
                active_blockers = [item for item in state.get("issues", []) if item.get("impact") == "blocking" and not item.get("invalidated_by")]
                if active_blockers:
                    raise AssertionError(f"exact reviewed repair left active blocker mirrors: {active_blockers}")
                if state["lifecycle"]["control"] == "BLOCKED":
                    cli("gate", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner",
                        "--revision", str(state["revision"]), "--phase", "EXECUTE", "--control", "ACTIVE",
                        "--reason", "current_repair_obligation_resolved", "--next-action", "continue_execution")
            processed.append(str(next_ticket["id"]))
            authoritative, _ = ledger.load_state(paths)
            source_ticket = next(item for item in authoritative["tickets"] if item["id"] == next_ticket["id"])
            next_ticket.update(source_ticket)
            write_ticket_artifact(paths["run"], next_ticket)
            assert_artifacts_match(paths["run"], authoritative["tickets"])
            if len(processed) == 10:
                state, _ = ledger.load_state(paths)
                cli("gate", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner", "--revision", str(state["revision"]), "--control", "QUIESCING", "--next-action", "qualification-pause")
                state, _ = ledger.load_state(paths)
                cli("gate", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner", "--revision", str(state["revision"]), "--control", "PAUSED", "--next-action", "qualification-resume")
                paused_seen = True
                state, _ = ledger.load_state(paths)
                cli("recover", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner", "--revision", str(state["revision"]), "--reason", "qualification-recovery")
                recovery_seen = True
                state, _ = ledger.load_state(paths)
                cli("gate", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner", "--revision", str(state["revision"]), "--phase", "EXECUTE", "--control", "ACTIVE", "--next-action", "qualification-continue")

        state, _ = ledger.load_state(paths)
        cli("gate", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner", "--revision", str(state["revision"]), "--phase", "VERIFY", "--control", "ACTIVE", "--gate-id", "G4", "--next-action", "qualification-verify")
        state, _ = ledger.load_state(paths)
        state = ledger.transaction(paths, "owner", int(state["revision"]), lambda current: current.setdefault("acceptance", []).append({"round": 1, "intent_revision": "v1", "candidate_fingerprint": "qualification-40", "verdict": "PASS", "transport": "automatic", "outcome_refs": []}))
        cli("gate", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner", "--revision", str(state["revision"]), "--phase", "ACCEPT", "--control", "ACTIVE", "--gate-id", "G5", "--next-action", "qualification-finalize")
        state, _ = ledger.load_state(paths)
        cli("gate", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner", "--revision", str(state["revision"]), "--phase", "ACCEPT", "--control", "ACCEPTED", "--gate-id", "G6", "--next-action", "terminal-finalization")

        final, raw = ledger.load_state(paths)
        round_trip = json.loads(raw.decode("utf-8"))
        ledger.validate_ledger(round_trip)
        projection = dashboard.project_ledger(final, paths["ledger"], raw)
        assert_artifacts_match(paths["run"], final["tickets"])
        if len(final["tickets"]) != 40 or len({ticket["id"] for ticket in final["tickets"]}) != 40:
            raise AssertionError("ticket loss or duplicate IDs")
        dependency_edges = sum(len(ticket["dependency_refs"]) for ticket in final["tickets"])
        if dependency_edges <= len(final["tickets"]):
            raise AssertionError("qualification DAG is not sufficiently nontrivial")
        if any(ticket["state"] != "INTEGRATED" for ticket in final["tickets"]):
            raise AssertionError("not all tickets integrated")
        if len(projection["tickets"]) != 40 or projection["ticket_counts"].get("INTEGRATED") != 40:
            raise AssertionError("dashboard projection truncated tickets")
        elapsed = time.monotonic() - started
        return {"qualified": True, "verdict": "40-TICKET QUALIFICATION PASS", "ticket_count": len(final["tickets"]), "dependency_edges": dependency_edges, "dag_depth": 40, "processed_integration_order": processed, "premature_readiness_rejected": premature.get("ok") is False, "repair_path": repair_seen, "pause_seen": paused_seen, "recovery_seen": recovery_seen, "terminal_control": final["lifecycle"]["control"], "settings": final["run_settings"], "schema_round_trip": ledger.canonical_bytes(round_trip) == raw, "dashboard_ticket_count": len(projection["tickets"]), "ledger_bytes": len(raw), "elapsed_seconds": round(elapsed, 3)}


def main() -> None:
    print(json.dumps(run_qualification(), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
