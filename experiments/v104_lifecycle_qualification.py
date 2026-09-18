#!/usr/bin/env python3
"""Offline v1.0.4 lifecycle qualification in a disposable Git repository."""

from __future__ import annotations

import json
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import ledger


CLI = ["python3", str(ROOT / "tools" / "ledger.py")]


def write_json(path: Path, value: object) -> None:
    ledger.atomic_write(path, ledger.canonical_bytes(value))


class Qualification:
    def __init__(self, root: Path):
        self.root = root
        self.control = root / "control"
        self.repo = root / "repo"
        self.control.mkdir(); self.repo.mkdir()
        self.run_id = "v104-synthetic"
        self.token = "owner-v104"
        self.expected_revision = 0
        self.events: list[dict[str, object]] = []
        self.pending_finding_by_ticket: dict[str, str] = {}
        self.call_git("init", "-q")
        ledger.atomic_write(self.repo / "README.md", b"# synthetic\n")
        (self.repo / "README.md").chmod(0o644)
        self.call_git("add", "README.md")
        self.call_git("-c", "user.name=Qualification", "-c", "user.email=qualification@example.invalid", "commit", "-qm", "baseline")

    @property
    def paths(self) -> dict[str, Path]:
        return ledger.paths(self.control, self.run_id)

    def state(self) -> tuple[dict[str, object], bytes]:
        return ledger.load_state(self.paths)

    def call_git(self, *args: str) -> str:
        result = subprocess.run(["git", *args], cwd=self.repo, text=True, capture_output=True)
        if result.returncode:
            raise AssertionError(f"git {' '.join(args)} failed: {result.stderr}")
        return result.stdout.strip()

    def call(self, *args: str, expect: int = 0) -> dict[str, object]:
        result = subprocess.run([*CLI, *args], text=True, capture_output=True)
        if result.returncode != expect:
            raise AssertionError(f"expected {expect}, got {result.returncode}: {' '.join(args)}\n{result.stdout}\n{result.stderr}")
        if expect:
            return {"error": json.loads(result.stderr)["error"]}
        return json.loads(result.stdout)

    def mutate(self, label: str, *args: str) -> dict[str, object]:
        before = self.expected_revision
        result = self.call(*args)
        self.expected_revision += 1
        if result.get("revision") != self.expected_revision:
            raise AssertionError(f"{label}: expected revision {self.expected_revision}, got {result}")
        state, raw = self.state()
        if state["revision"] != self.expected_revision:
            raise AssertionError(f"{label}: ledger revision mismatch")
        self.events.append({"label": label, "before": before, "after": self.expected_revision, "ledger_hash": ledger.sha256_bytes(raw), "next_action": state["lifecycle"]["next_action"]["kind"]})
        return result

    def idempotent(self, label: str, *args: str) -> dict[str, object]:
        before = self.paths["ledger"].read_bytes()
        result = self.call(*args)
        if not result.get("idempotent") or self.paths["ledger"].read_bytes() != before or result.get("revision") != self.expected_revision:
            raise AssertionError(f"{label}: retry was not zero-effect: {result}")
        self.events.append({"label": label, "before": self.expected_revision, "after": self.expected_revision, "idempotent": True, "ledger_hash": ledger.sha256_bytes(before)})
        return result

    def observe_runtime(
        self, attempt_id: str, event: str, event_id: str, *, instance: str,
        return_hash: str | None = None,
    ) -> None:
        state, _ = self.state()
        attempt = ledger.attempt_by_id(state, attempt_id)
        receipt = {
            "kind": "runtime_observation", "event_id": event_id, "event": event,
            "run_id": self.run_id, "attempt_id": attempt_id, "epoch": attempt["epoch"],
            "packet_hash": attempt["packet_hash"], "spawn_request_id": attempt["runtime"]["spawn_request_id"],
            "runtime_instance_id": instance, "observed_at": "2026-09-18T12:00:00Z",
            "observer": "runtime-adapter-test", "runtime_build": "fixture-1", "return_hash": return_hash,
            "coverage": {"scope": "test process tree", "descendant_writers": "included" if event == "stop" else "not_applicable"},
        }
        event_path = self.paths["run"] / f"{event_id}.json"
        write_json(event_path, receipt)
        self.mutate(
            f"runtime-{attempt_id}-{event}", "observe-runtime", "--control-root", str(self.control),
            "--run-id", self.run_id, "--owner-token", self.token,
            "--revision", str(state["revision"]), "--attempt-id", attempt_id,
            "--event", event, "--event-id", event_id, "--event-file", str(event_path),
        )

    def bootstrap(self) -> None:
        result = self.call("init", "--control-root", str(self.control), "--repo-root", str(self.repo), "--run-id", self.run_id, "--owner-token", self.token)
        if result["revision"] != 0:
            raise AssertionError("init did not create revision 0")
        self.events.append({"label": "init", "before": None, "after": 0, "ledger_hash": ledger.sha256_file(self.paths["ledger"])})
        before, _ = self.state()
        def bind_checkout(state: dict[str, object]) -> None:
            state["repository"].update({
                "checkout": str(self.repo), "branch": self.call_git("branch", "--show-current"),
                "initial_head": self.call_git("rev-parse", "HEAD"),
            })
        bound = ledger.transaction(self.paths, self.token, before["revision"], bind_checkout)
        self.expected_revision = int(bound["revision"])
        self.events.append({"label": "bind-checkout", "before": before["revision"], "after": self.expected_revision, "ledger_hash": ledger.sha256_file(self.paths["ledger"])})
        self.mutate("interrupted-bootstrap-recovery", "recover", "--control-root", str(self.control), "--run-id", self.run_id, "--owner-token", self.token, "--revision", str(self.expected_revision), "--reason", "interrupted_bootstrap")
        intent_v1 = self.root / "intent-v1.md"; ledger.atomic_write(intent_v1, b"# Intent v1\n\nR-1 and R-2.\n")
        self.mutate("publish-intent", "publish-intent", "--control-root", str(self.control), "--run-id", self.run_id, "--owner-token", self.token, "--revision", str(self.expected_revision), "--intent-file", str(intent_v1), "--doc-id", "D-intent-v1", "--doc-version", "v1", "--intent-revision", "1")
        self.mutate("finish-bootstrap-recovery", "gate", "--control-root", str(self.control), "--run-id", self.run_id, "--owner-token", self.token, "--revision", str(self.expected_revision), "--phase", "INTENT", "--control", "ACTIVE", "--reason", "reconciled", "--next-action", "g1_build")
        intent_v2 = self.root / "intent-v2.md"; ledger.atomic_write(intent_v2, b"# Intent v2\n\nR-1 and R-2 with explicit C-1 and C-2.\n")
        self.mutate("amend-intent", "amend", "--control-root", str(self.control), "--run-id", self.run_id, "--owner-token", self.token, "--revision", str(self.expected_revision), "--intent-file", str(intent_v2), "--doc-id", "D-intent-v2", "--doc-version", "v2", "--intent-revision", "2", "--amendment-id", "AM-1", "--authority-ref", "synthetic-user")
        self.mutate("g1-to-design", "gate", "--control-root", str(self.control), "--run-id", self.run_id, "--owner-token", self.token, "--revision", str(self.expected_revision), "--phase", "DESIGN", "--control", "BLOCKED", "--reason", "criteria_publication_gap", "--next-action", "adopt-requirements")
        state, _ = self.state()
        manifest = {
            "publication_id": "RP-v2", "version": "v2", "epoch": 0, "intent_revision": "2", "intent_document_ref": "D-intent-v2", "intent_document_hash": state["intent"]["document_hash"],
            "requirements": [
                {"id": "R-1", "version": "v2", "status": "active", "provenance_refs": ["D-intent-v2"], "criterion_refs": ["C-1"]},
                {"id": "R-2", "version": "v2", "status": "active", "provenance_refs": ["D-intent-v2"], "criterion_refs": ["C-2"]},
            ],
            "criteria": [
                {"id": "C-1", "version": "v2", "requirement_refs": ["R-1"], "oracle": "app-one oracle", "status": "active", "source_ref": "D-intent-v2"},
                {"id": "C-2", "version": "v2", "requirement_refs": ["R-2"], "oracle": "app-two oracle", "status": "active", "source_ref": "D-intent-v2"},
            ],
        }
        manifest_path = self.root / "requirements-v2.json"; write_json(manifest_path, manifest)
        self.mutate("adopt-requirements", "adopt-requirements", "--control-root", str(self.control), "--run-id", self.run_id, "--owner-token", self.token, "--revision", str(self.expected_revision), "--manifest", str(manifest_path))
        self.idempotent("adopt-requirements-lost-response", "adopt-requirements", "--control-root", str(self.control), "--run-id", self.run_id, "--owner-token", self.token, "--revision", str(self.expected_revision - 1), "--manifest", str(manifest_path))

    def make_bundle(self, version: int) -> Path:
        state, _ = self.state()
        docs = []
        for name, kind in (("design", "design"), ("interfaces", "interfaces"), ("manifest", "manifest"), ("plan", "plan"), ("tickets", "tickets"), ("routes", "routes")):
            source = self.root / f"{name}-v{version}.md"; ledger.atomic_write(source, f"# {name} v{version}\n".encode())
            docs.append({"id": f"D-{name}-v{version}", "version": f"v{version}", "kind": kind, "source": str(source), "hash": ledger.sha256_file(source)})
        bundle = {
            "bundle_id": f"B-v{version}", "version": f"v{version}", "epoch": 0, "intent_revision": "2", "intent_document_ref": "D-intent-v2", "intent_document_hash": state["intent"]["document_hash"],
            "documents": docs,
            "contracts": [
                {"id": f"K-1-v{version}", "version": f"v{version}", "status": "active", "provenance_refs": [f"D-interfaces-v{version}"], "implementation_availability": "available", "implementation_availability_evidence_refs": [f"fixture:K-1-v{version}-available"]},
                {"id": f"K-2-v{version}", "version": f"v{version}", "status": "active", "provenance_refs": [f"D-interfaces-v{version}"], "implementation_availability": "available", "implementation_availability_evidence_refs": [f"fixture:K-2-v{version}-available"]},
            ],
            "tickets": [
                {"id": f"T-1-v{version}", "goal_ref": "G-1", "criterion_refs": ["C-1"], "contract_refs": [f"K-1-v{version}"], "dependency_refs": [], "state": "PLANNED", "complexity": "bounded", "risk": "routine", "zone": [{"path": "app-one.txt", "operations": ["create", "modify"]}]},
                {"id": f"T-2-v{version}", "goal_ref": "G-2", "criterion_refs": ["C-2"], "contract_refs": [f"K-2-v{version}"], "dependency_refs": [f"T-1-v{version}"], "state": "PLANNED", "complexity": "bounded", "risk": "routine", "zone": [{"path": "app-two.txt", "operations": ["create", "modify"]}]},
            ],
            "routes": [{"id": f"ROUTE-v{version}", "capability": "worker/reviewer", "reasoning": "offline synthetic qualification", "adequacy": "CONFIRMED", "context_grade": "PACKET_SCOPED"}],
        }
        path = self.root / f"bundle-v{version}.json"; write_json(path, bundle); return path

    def publish_bundle(self, version: int) -> None:
        path = self.make_bundle(version)
        result = self.mutate(f"publish-design-v{version}", "publish-design-bundle", "--control-root", str(self.control), "--run-id", self.run_id, "--owner-token", self.token, "--revision", str(self.expected_revision), "--bundle", str(path))
        self.idempotent(f"publish-design-v{version}-lost-response", "publish-design-bundle", "--control-root", str(self.control), "--run-id", self.run_id, "--owner-token", self.token, "--revision", str(self.expected_revision - 1), "--bundle", str(path))
        if result["publication_hash"] != self.state()[0]["design_publication"]["publication_hash"]:
            raise AssertionError("publication fingerprint drift")

    def design_review(self, review_kind: str, verdict: str, suffix: str) -> None:
        state, _ = self.state(); publication = state["design_publication"]
        attempt_id = f"A-{review_kind}-{suffix}"
        packet = {
            "identity": {"run_id": self.run_id, "attempt_id": attempt_id, "epoch": 0, "source_revision": self.expected_revision, "registration_revision": self.expected_revision, "subject_revision": publication["published_revision"], "intent_revision": "2", "intent_document_ref": "D-intent-v2", "intent_document_hash": state["intent"]["document_hash"]},
            "kind": "review", "mandate": f"design-{review_kind}", "subject_fingerprint": publication["publication_hash"], "criteria": [{"criterion_id": "C-1"}, {"criterion_id": "C-2"}], "axes": [review_kind], "return_target": {"path": "return.json"},
        }
        packet_path = self.root / f"{attempt_id}-packet.json"; write_json(packet_path, packet)
        self.mutate(f"prepare-{attempt_id}", "prepare-design-review", "--control-root", str(self.control), "--run-id", self.run_id, "--owner-token", self.token, "--revision", str(self.expected_revision), "--review-attempt-id", attempt_id, "--lease-id", f"L-{attempt_id}", "--packet", str(packet_path), "--review-kind", review_kind, "--reviewer-identity", f"{review_kind}@example.invalid", "--reviewer-role", f"independent-{review_kind}")
        attempt = ledger.attempt_by_id(self.state()[0], attempt_id)
        outcome = "fulfilled" if verdict == "PASS" else "missing"
        check_outcome = "fulfilled" if verdict == "PASS" else "failed"
        payload = {"identity": {**packet["identity"], "packet_hash": attempt["packet_hash"]}, "subject_fingerprint": publication["publication_hash"], "verdict": verdict, "coverage": [{"criterion_id": "C-1", "outcome": outcome, "evidence_refs": [f"EV-{attempt_id}"]}, {"criterion_id": "C-2", "outcome": outcome, "evidence_refs": [f"EV-{attempt_id}"]}], "checks": [{"check_id": f"check-{review_kind}", "axis": review_kind, "outcome": check_outcome, "actual": verdict, "evidence_ref": f"EV-{attempt_id}"}], "context_refs": ["offline-clean-fixture"], "findings": []}
        inbox = self.paths["scratch"] / attempt_id / "return.json"; write_json(inbox, payload)
        self.call("validate-return", "--control-root", str(self.control), "--run-id", self.run_id, "--attempt-id", attempt_id, "--return-file", str(inbox), "--kind", "review")
        runtime_instance = f"runtime-{attempt_id}"
        self.observe_runtime(attempt_id, "start", f"OBS-{attempt_id}-START", instance=runtime_instance)
        self.observe_runtime(attempt_id, "stop", f"OBS-{attempt_id}-STOP", instance=runtime_instance)
        self.mutate(f"ingest-{attempt_id}-{verdict.lower()}", "ingest-return", "--control-root", str(self.control), "--run-id", self.run_id, "--owner-token", self.token, "--revision", str(self.expected_revision), "--attempt-id", attempt_id, "--return-file", str(inbox), "--kind", "review")
        self.idempotent(f"ingest-{attempt_id}-lost-response", "ingest-return", "--control-root", str(self.control), "--run-id", self.run_id, "--owner-token", self.token, "--revision", str(self.expected_revision - 1), "--attempt-id", attempt_id, "--return-file", str(inbox), "--kind", "review")
        if ledger.attempt_by_id(self.state()[0], attempt_id)["lease"]["state"] != "released":
            raise AssertionError("terminal reviewer lease was not released")

    def design_cycle(self) -> None:
        self.publish_bundle(1)
        self.design_review("coverage", "BLOCK", "v1")
        self.design_review("plan", "BLOCK", "v1")
        if any(item["type"] == "reviewer_disagreement" for item in self.state()[0].get("issues", [])):
            raise AssertionError("mixed design mandates produced false disagreement")
        self.publish_bundle(2)
        self.design_review("coverage", "PASS", "v2")
        self.design_review("plan", "BLOCK", "v2")
        if any(item["type"] == "reviewer_disagreement" and item.get("impact") == "blocking" for item in self.state()[0].get("issues", [])):
            raise AssertionError("coverage PASS and plan BLOCK produced false disagreement")
        self.publish_bundle(3)
        self.design_review("coverage", "PASS", "v3")
        self.design_review("plan", "PASS", "v3")
        self.mutate("g2-g3-to-plan", "gate", "--control-root", str(self.control), "--run-id", self.run_id, "--owner-token", self.token, "--revision", str(self.expected_revision), "--phase", "PLAN", "--control", "ACTIVE", "--gate-id", "G3", "--reason", "current_g2_g3_pass", "--next-action", "g3_pass")
        self.mutate("plan-to-execute", "gate", "--control-root", str(self.control), "--run-id", self.run_id, "--owner-token", self.token, "--revision", str(self.expected_revision), "--phase", "EXECUTE", "--control", "ACTIVE", "--reason", "execution_ready", "--next-action", "execute_tickets")

    def baseline(self, name: str) -> Path:
        files = []
        for path in sorted(self.repo.rglob("*")):
            rel = path.relative_to(self.repo)
            if ".git" in rel.parts or path.is_symlink() or not path.is_file():
                continue
            files.append({"path": rel.as_posix(), "type": "file", "mode": stat.S_IMODE(path.stat().st_mode), "sha256": ledger.sha256_file(path)})
        target = self.root / f"{name}-baseline.json"; write_json(target, {"files": files}); return target

    def worker_candidate(self, ticket_id: str, criterion_id: str, attempt_id: str, filename: str, content: str, *, repair: dict[str, str] | None = None, ready: bool = True) -> str:
        if ready:
            self.mutate(f"ready-{ticket_id}", "ready-ticket", "--control-root", str(self.control), "--run-id", self.run_id, "--owner-token", self.token, "--revision", str(self.expected_revision), "--ticket-id", ticket_id)
        state, _ = self.state()
        ticket = next(item for item in state["tickets"] if item["id"] == ticket_id)
        intent = ledger.current_intent_binding(state)
        publication = state["design_publication"]
        candidate = ledger.current_candidate_record(state, ticket)
        base = candidate.get("sha") if candidate is not None else state["repository"].get("initial_head")
        if not base:
            raise AssertionError("fixture checkout has no exact current candidate/base")
        self.call_git("switch", "--create", f"qualification-{attempt_id}", str(base))
        baseline = self.baseline(attempt_id)
        operation = "modify" if (self.repo / filename).exists() else "create"
        identity = {
            "run_id": self.run_id, "ticket_id": ticket_id, "attempt_id": attempt_id, "epoch": 0,
            "source_revision": self.expected_revision, "intent_revision": intent["revision"],
            "intent_document_ref": intent["document_ref"], "intent_document_hash": intent["document_hash"],
            "design_publication_ref": publication["id"], "design_publication_hash": publication["publication_hash"],
            "design_publication_revision": publication["published_revision"],
            "contract_refs": sorted(ticket.get("contract_refs", [])),
        }
        packet = {"identity": identity, "intent_revision": intent["revision"], "intent_document_ref": intent["document_ref"], "intent_document_hash": intent["document_hash"], "kind": "worker", "mode": "repair" if repair else "implement", "goal": f"implement {ticket_id}", "acceptance": [{"criterion_id": criterion_id}], "workspace": {"root": str(self.repo), "expected_base": base}, "write": {"allow": [{"path": filename, "operations": ["create", "modify"]}]}, "verification": [{"check_id": f"oracle-{criterion_id}", "criterion_refs": [criterion_id], "required": True}], "risk": {"level": "routine"}, "context": [{"ref": "contracts/worker.md"}], "return_target": {"path": "return.json"}}
        if repair:
            packet["repair"] = repair
        packet_path = self.root / f"{attempt_id}-packet.json"; write_json(packet_path, packet)
        self.mutate(f"dispatch-{attempt_id}", "dispatch", "--control-root", str(self.control), "--run-id", self.run_id, "--owner-token", self.token, "--revision", str(self.expected_revision), "--ticket-id", ticket_id, "--attempt-id", attempt_id, "--lease-id", f"L-{attempt_id}", "--route-id", "ROUTE-v3", "--packet", str(packet_path))
        self.idempotent(f"dispatch-{attempt_id}-lost-response", "dispatch", "--control-root", str(self.control), "--run-id", self.run_id, "--owner-token", self.token, "--revision", str(self.expected_revision - 1), "--ticket-id", ticket_id, "--attempt-id", attempt_id, "--lease-id", f"L-{attempt_id}", "--route-id", "ROUTE-v3", "--packet", str(packet_path))
        runtime_instance = f"runtime-{attempt_id}"
        self.observe_runtime(attempt_id, "start", f"OBS-{attempt_id}-START", instance=runtime_instance)
        ledger.atomic_write(self.repo / filename, content.encode())
        (self.repo / filename).chmod(0o644)
        self.observe_runtime(attempt_id, "stop", f"OBS-{attempt_id}-STOP", instance=runtime_instance)
        attempt = ledger.attempt_by_id(self.state()[0], attempt_id)
        payload = {"identity": {**packet["identity"], "packet_hash": attempt["packet_hash"]}, "status": "DONE", "result": "implemented", "files": [{"path": filename, "operation": operation}], "checks": [{"check_id": f"oracle-{criterion_id}", "outcome": "pass", "actual": content.strip(), "evidence_ref": f"EV-{attempt_id}"}], "criteria": [{"criterion_id": criterion_id, "outcome": "satisfied", "evidence_refs": [f"EV-{attempt_id}"]}]}
        inbox = self.paths["scratch"] / attempt_id / "return.json"; write_json(inbox, payload)
        self.call("validate-return", "--control-root", str(self.control), "--run-id", self.run_id, "--attempt-id", attempt_id, "--return-file", str(inbox), "--kind", "worker")
        self.mutate(f"ingest-{attempt_id}", "ingest-return", "--control-root", str(self.control), "--run-id", self.run_id, "--owner-token", self.token, "--revision", str(self.expected_revision), "--attempt-id", attempt_id, "--return-file", str(inbox), "--kind", "worker")
        declared = self.root / f"{attempt_id}-declared.json"; zone = self.root / f"{attempt_id}-zone.json"
        write_json(declared, [{"path": filename}]); write_json(zone, [{"path": filename, "operations": ["create", "modify"]}])
        audit = self.call("audit-write-set", "--root", str(self.repo), "--baseline", str(baseline), "--declared", str(declared), "--zone", str(zone))
        if not audit["pass"]:
            raise AssertionError(f"write audit failed: {audit}")
        operation_id = f"OP-{attempt_id}"
        authority_ref = "synthetic-run"
        if repair:
            state, _ = self.state()
            authorization = next((
                item for item in state.get("decisions", [])
                if item.get("type") == "repair_authorization"
                and item.get("status") in ("authorized", "consumed")
                and item.get("consumed_by") in (None, attempt_id)
                and ticket_id in item.get("affected_refs", [])
                and repair.get("finding_ref") in item.get("affected_refs", [])
            ), None)
            if authorization is None:
                raise AssertionError("repair candidate commit has no exact active authorization")
            authority_ref = authorization["id"]
        self.mutate(f"prepare-effect-{attempt_id}", "prepare-effect", "--control-root", str(self.control), "--run-id", self.run_id, "--owner-token", self.token, "--revision", str(self.expected_revision), "--operation-id", operation_id, "--kind", "candidate_commit", "--target", str(self.repo), "--expected-before", base, "--authority-ref", authority_ref)
        self.idempotent(f"prepare-effect-{attempt_id}-lost-response", "prepare-effect", "--control-root", str(self.control), "--run-id", self.run_id, "--owner-token", self.token, "--revision", str(self.expected_revision - 1), "--operation-id", operation_id, "--kind", "candidate_commit", "--target", str(self.repo), "--expected-before", base, "--authority-ref", authority_ref)
        self.call_git("add", filename); self.call_git("-c", "user.name=Qualification", "-c", "user.email=qualification@example.invalid", "commit", "-qm", f"candidate {attempt_id}")
        commit = self.call_git("rev-parse", "HEAD"); tree = self.call_git("rev-parse", "HEAD^{tree}")
        receipt = self.root / f"{attempt_id}-receipt.json"; write_json(receipt, {"status": "PASS", "run_id": self.run_id, "ticket_id": ticket_id, "attempt_id": attempt_id, "operation_id": operation_id, "kind": "candidate_commit", "target": str(self.repo), "checkout": str(self.repo), "expected_before": base, "base_sha": base, "intended_after": commit, "commit_sha": commit, "tree_sha": tree, "authority_ref": authority_ref, "receipt_ref": f"git:{commit}"})
        self.mutate(f"candidate-{attempt_id}", "candidate", "--control-root", str(self.control), "--run-id", self.run_id, "--owner-token", self.token, "--revision", str(self.expected_revision), "--attempt-id", attempt_id, "--commit-receipt", str(receipt), "--operation-id", operation_id)
        self.idempotent(f"candidate-{attempt_id}-lost-response", "candidate", "--control-root", str(self.control), "--run-id", self.run_id, "--owner-token", self.token, "--revision", str(self.expected_revision - 1), "--attempt-id", attempt_id, "--commit-receipt", str(receipt), "--operation-id", operation_id)
        return commit

    def change_review(self, ticket_id: str, criterion_id: str, worker_attempt_id: str, review_attempt_id: str, verdict: str) -> str | None:
        state, _ = self.state(); worker = ledger.attempt_by_id(state, worker_attempt_id)
        packet = {"identity": {"run_id": self.run_id, "ticket_id": ticket_id, "attempt_id": review_attempt_id, "epoch": 0, "source_revision": self.expected_revision, "registration_revision": self.expected_revision, "subject_revision": self.expected_revision, "intent_revision": "2"}, "kind": "review", "mandate": "change-correctness", "subject_fingerprint": worker["candidate_sha"], "criteria": [{"criterion_id": criterion_id}], "axes": ["correctness"], "return_target": {"path": "return.json"}}
        packet_path = self.root / f"{review_attempt_id}-packet.json"; write_json(packet_path, packet)
        self.mutate(f"prepare-{review_attempt_id}", "prepare-review", "--control-root", str(self.control), "--run-id", self.run_id, "--owner-token", self.token, "--revision", str(self.expected_revision), "--ticket-id", ticket_id, "--review-attempt-id", review_attempt_id, "--lease-id", f"L-{review_attempt_id}", "--packet", str(packet_path))
        attempt = ledger.attempt_by_id(self.state()[0], review_attempt_id)
        runtime_instance = f"runtime-{review_attempt_id}"
        self.observe_runtime(review_attempt_id, "start", f"OBS-{review_attempt_id}-START", instance=runtime_instance)
        self.observe_runtime(review_attempt_id, "stop", f"OBS-{review_attempt_id}-STOP", instance=runtime_instance)
        state = self.state()[0]
        worker = ledger.attempt_by_id(state, worker_attempt_id)
        outcome = "fulfilled" if verdict == "PASS" else "missing"
        payload = {"identity": {**packet["identity"], "packet_hash": attempt["packet_hash"]}, "subject_fingerprint": worker["candidate_sha"], "verdict": verdict, "coverage": [{"criterion_id": criterion_id, "outcome": outcome, "evidence_refs": [f"EV-{review_attempt_id}"]}], "checks": [{"check_id": "correctness", "axis": "correctness", "outcome": "fulfilled" if verdict == "PASS" else "failed", "actual": verdict, "evidence_ref": f"EV-{review_attempt_id}"}], "context_refs": ["offline-independent"], "findings": [] if verdict == "PASS" else [{"axis": "correctness", "impact": "blocking", "claim": "candidate needs repair", "expected": "correct", "actual": "defect", "evidence": f"EV-{review_attempt_id}", "affected_refs": [ticket_id]}]}
        finding_ref = self.pending_finding_by_ticket.get(ticket_id)
        if verdict == "PASS" and finding_ref:
            payload["finding_resolution"] = [{
                "finding_ref": finding_ref,
                "candidate_ref": f"candidate-{worker_attempt_id}",
                "evidence_refs": [f"EV-{review_attempt_id}"],
                "reason": "The fresh PASS review verifies the exact repaired finding on the current candidate.",
            }]
        inbox = self.paths["scratch"] / review_attempt_id / "return.json"; write_json(inbox, payload)
        self.call("validate-return", "--control-root", str(self.control), "--run-id", self.run_id, "--attempt-id", review_attempt_id, "--return-file", str(inbox), "--kind", "review")
        if verdict != "PASS":
            self.mutate(f"ingest-{review_attempt_id}-block", "ingest-return", "--control-root", str(self.control), "--run-id", self.run_id, "--owner-token", self.token, "--revision", str(self.expected_revision), "--attempt-id", review_attempt_id, "--return-file", str(inbox), "--kind", "review")
            state, _ = self.state()
            finding = next(item for item in reversed(state["findings"]) if item.get("source_ref") == review_attempt_id and ticket_id in item.get("affected_refs", []))
            self.pending_finding_by_ticket[ticket_id] = finding["id"]
            return finding["id"]
        state, raw = self.state(); integrity = self.root / f"{review_attempt_id}-integrity.json"; write_json(integrity, {"status": "PASS", "candidate_fingerprint": worker["candidate_sha"], "ledger_hash": ledger.sha256_bytes(raw)})
        self.mutate(f"integrate-{review_attempt_id}", "integrate", "--control-root", str(self.control), "--run-id", self.run_id, "--owner-token", self.token, "--revision", str(self.expected_revision), "--attempt-id", review_attempt_id, "--review-file", str(inbox), "--integrity-receipt", str(integrity), "--review-id", f"REV-{review_attempt_id}")
        self.pending_finding_by_ticket.pop(ticket_id, None)
        return None

    def execute(self) -> tuple[str, str]:
        ticket1, ticket2 = "T-1-v3", "T-2-v3"
        self.worker_candidate(ticket1, "C-1", "A-T1-1", "app-one.txt", "BROKEN\n")
        finding_ref = self.change_review(ticket1, "C-1", "A-T1-1", "A-T1-review-1", "BLOCK")
        assert finding_ref
        repair = {"cause": "implementation", "finding_ref": finding_ref, "hypothesis": "replace broken fixture value", "expected_proof": "review observes FIXED", "stopping_condition": "correctness review passes", "causal_change": "replace BROKEN with FIXED"}
        repair_path = self.root / "repair.json"; write_json(repair_path, repair)
        self.mutate("authorize-t1-repair", "authorize-repair", "--control-root", str(self.control), "--run-id", self.run_id, "--owner-token", self.token, "--revision", str(self.expected_revision), "--ticket-id", ticket1, "--finding-ref", finding_ref, "--authorization-id", "AUTH-T1-1", "--repair-contract", str(repair_path))
        candidate1 = self.worker_candidate(ticket1, "C-1", "A-T1-2", "app-one.txt", "FIXED\n", repair=repair, ready=False)
        self.change_review(ticket1, "C-1", "A-T1-2", "A-T1-review-2", "PASS")
        state, _ = self.state()
        if ledger.open_ticket_finding_obligations(state, ticket1):
            raise AssertionError(f"exact reviewed repair left the ticket obligation open: {ledger.open_ticket_finding_obligations(state, ticket1)}")
        active_blockers = [item for item in state.get("issues", []) if item.get("impact") == "blocking" and not item.get("invalidated_by")]
        if active_blockers:
            raise AssertionError(f"exact reviewed repair left active blocker mirrors: {active_blockers}")
        if state["lifecycle"]["control"] == "BLOCKED":
            self.mutate("resume-after-repair", "gate", "--control-root", str(self.control), "--run-id", self.run_id, "--owner-token", self.token, "--revision", str(self.expected_revision), "--phase", "EXECUTE", "--control", "ACTIVE", "--reason", "current_repair_obligation_resolved", "--next-action", "continue_execution")
        candidate2 = self.worker_candidate(ticket2, "C-2", "A-T2-1", "app-two.txt", "DONE\n")
        self.change_review(ticket2, "C-2", "A-T2-1", "A-T2-review-1", "PASS")
        self.mutate("g4-to-verify", "gate", "--control-root", str(self.control), "--run-id", self.run_id, "--owner-token", self.token, "--revision", str(self.expected_revision), "--phase", "VERIFY", "--control", "ACTIVE", "--gate-id", "G4", "--reason", "g4_pass", "--next-action", "prepare_g5")
        return candidate1, candidate2

    def accept(self, candidate: str) -> None:
        state, _ = self.state()
        attempt_id = "A-T2-g5"
        ticket = next(item for item in state["tickets"] if item["id"] == "T-2-v3")
        candidate_record = ledger.current_candidate_record(state, ticket)
        if candidate_record is None:
            raise AssertionError("G5 requires the exact current T-2 candidate")
        initial_packet = {
            "identity": {
                "run_id": self.run_id, "ticket_id": ticket["id"], "attempt_id": attempt_id,
                "epoch": 0, "source_revision": self.expected_revision,
                "registration_revision": self.expected_revision, "subject_revision": self.expected_revision,
                "intent_revision": "2",
            },
            "kind": "review", "mandate": "independent product acceptance",
            "subject_fingerprint": candidate_record["sha"], "criteria": [{"criterion_id": "C-2"}],
            "axes": ["product-acceptance"], "return_target": {"path": "acceptance.json"},
        }
        initial_packet_path = self.root / f"{attempt_id}-registration.json"
        write_json(initial_packet_path, initial_packet)
        packet_raw = initial_packet_path.read_bytes()
        packet_hash = ledger.sha256_bytes(packet_raw)
        packet_ref = f"objects/{ledger.object_store(self.paths, packet_raw)}"
        before_revision = self.expected_revision
        def register_g5_review(state: dict[str, object]) -> None:
            worker = ledger.current_candidate_producer(state, ticket)
            if worker is None or worker.get("candidate_sha") != candidate_record["sha"]:
                raise AssertionError("G5 reviewer registration lost its exact candidate producer")
            attempt = {
                "id": attempt_id, "kind": "review", "mode": "change", "subject_ref": ticket["id"],
                "packet_ref": packet_ref, "packet_hash": packet_hash, "epoch": state["owner"]["epoch"],
                "state": "PREPARED", "lease": {"id": f"L-{attempt_id}", "state": "active", "zone": []},
                "route_ref": None, "checkout": None, "base_sha": worker["candidate_sha"],
                "candidate_sha": worker["candidate_sha"], "candidate_tree_sha": worker["candidate_tree_sha"],
                "return_ref": None, "finding_refs": [], "subject_fingerprint": worker["candidate_sha"],
                "packet_registration_revision": state["revision"], "packet_source_revision": state["revision"],
                "subject_revision": state["revision"], "attempt_created_revision": state["revision"] + 1,
                "return_source_revision": None,
            }
            ledger.initialize_attempt_runtime(self.run_id, attempt)
            binding = ledger.current_intent_binding(state)
            attempt.update({
                "intent_revision": binding["revision"], "intent_document_ref": binding["document_ref"],
                "intent_document_hash": binding["document_hash"],
            })
            state["attempts"].append(attempt)
            ledger.add_usage(state.setdefault("usage", ledger.default_usage()).setdefault("counters", ledger.zero_usage()), {"packet_bytes": len(packet_raw), "attempt_registrations": 1})
            state["lifecycle"]["next_action"] = {"kind": "prepare_g5_handoff", "subject_refs": [attempt_id], "preconditions": ["exact integrated candidate remains current"], "read_refs": ["phases/accept.md"]}
        registered = ledger.transaction(self.paths, self.token, before_revision, register_g5_review)
        self.expected_revision = int(registered["revision"])
        self.events.append({"label": "prepare-g5-reviewer", "before": before_revision, "after": self.expected_revision, "ledger_hash": ledger.sha256_file(self.paths["ledger"])})
        state, _ = self.state(); review_attempt = ledger.attempt_by_id(state, attempt_id)
        export = self.root / "candidate-export"; export.mkdir()
        for ticket_id, filename in (("T-1-v3", "app-one.txt"), ("T-2-v3", "app-two.txt")):
            ticket = next(item for item in state["tickets"] if item["id"] == ticket_id)
            current_candidate = ledger.current_candidate_record(state, ticket)
            if current_candidate is None:
                raise AssertionError(f"missing exact candidate for manual acceptance export: {ticket_id}")
            content = subprocess.run(
                ["git", "-C", str(self.repo), "show", f"{current_candidate['sha']}:{filename}"],
                check=True, capture_output=True,
            ).stdout
            ledger.atomic_write(export / filename, content)
        bundle_root = self.root / "g5-bundle"
        packet = {"identity": {"run_id": self.run_id, "attempt_id": attempt_id, "epoch": 0, "source_revision": self.expected_revision, "intent_revision": "2", "intent_document_ref": "D-intent-v2", "intent_document_hash": state["intent"]["document_hash"]}, "kind": "acceptance", "mandate": "independent product acceptance", "subject_fingerprint": candidate, "criteria": [{"id": "C-1", "requirement_id": "R-1", "oracle": "app-one FIXED"}, {"id": "C-2", "requirement_id": "R-2", "oracle": "app-two DONE"}], "axes": ["product-acceptance"], "constraints": ["offline"], "subject": {"candidate_sha": candidate, "candidate_tree_sha": review_attempt["candidate_tree_sha"], "export_label": "synthetic", "pristine_check_required": True}, "return_target": {"path": "acceptance.json"}}
        projection = {"kind": "acceptance_projection", "intent_revision": "2", "intent_document_ref": "D-intent-v2", "intent_document_hash": state["intent"]["document_hash"], "candidate_fingerprint": candidate, "goal": "synthetic lifecycle", "criteria": [{"id": "C-1", "requirement_id": "R-1", "oracle": "app-one FIXED"}, {"id": "C-2", "requirement_id": "R-2", "oracle": "app-two DONE"}], "exclusions": [], "return_schema": "acceptance_return"}
        packet_path = self.root / "g5-packet.json"; projection_path = self.root / "g5-projection.json"; write_json(packet_path, packet); write_json(projection_path, projection)
        handoff = self.mutate("prepare-g5-handoff", "prepare-handoff", "--control-root", str(self.control), "--run-id", self.run_id, "--owner-token", self.token, "--revision", str(self.expected_revision), "--attempt-id", attempt_id, "--packet", str(packet_path), "--projection", str(projection_path), "--export-root", str(export), "--bundle-root", str(bundle_root))
        attempt = ledger.attempt_by_id(self.state()[0], attempt_id)
        inventory = [{"path": f"candidate-export/{name}", "sha256": ledger.sha256_file(export / name)} for name in ("app-one.txt", "app-two.txt")]
        env = {"receipt_id": "ENV-G5", "status": "PASS", "topology": {"surface": "offline-disposable"}, "inventory_hashes": inventory, "effective_grants": {"authoritative_repo": False}, "boundary_probes": [{"probe": "authority", "result": "absent"}], "authoritative_absent": True}
        context = {"receipt_id": "CTX-G5", "status": "PASS", "grade": "MANUAL_ATTESTED_CLEAN", "packet_hash": attempt["packet_hash"], "export_hash": handoff["manifest_sha256"], "clean_input": True, "contamination_absent": True, "session_provenance": {"fixture": "offline"}}
        env_path = self.root / "environment.json"; context_path = self.root / "context.json"; write_json(env_path, env); write_json(context_path, context)
        base_return = {"identity": {"run_id": self.run_id, "attempt_id": attempt_id, "packet_hash": attempt["packet_hash"], "epoch": 0, "source_revision": packet["identity"]["source_revision"], "intent_revision": "2", "intent_document_ref": "D-intent-v2", "intent_document_hash": state["intent"]["document_hash"]}, "candidate_fingerprint": candidate, "verdict": "PASS", "outcomes": [{"criterion_id": "C-1", "outcome": "fulfilled", "evidence_refs": ["EV-G5-1"]}, {"criterion_id": "C-2", "outcome": "fulfilled", "evidence_refs": ["EV-G5-2"]}], "checks": [{"check_id": "product-acceptance", "outcome": "fulfilled", "actual": "fixture passed", "evidence_ref": "EV-G5"}], "findings": []}
        return_hash = ledger.sha256_bytes(ledger.canonical_bytes(base_return))
        runtime_instance = "runtime-A-T2-review-1"
        self.observe_runtime(attempt_id, "start", "OBS-A-T2-G5-START", instance=runtime_instance)
        self.observe_runtime(attempt_id, "return_observed", "OBS-A-T2-G5-RETURN", instance=runtime_instance, return_hash=return_hash)
        self.observe_runtime(attempt_id, "stop", "OBS-A-T2-G5-STOP", instance=runtime_instance)
        state, _ = self.state()
        inbox_root = self.paths["scratch"] / attempt_id
        stale = dict(base_return); stale["candidate_fingerprint"] = "0" * 40; stale_path = inbox_root / "stale-acceptance.json"; write_json(stale_path, stale)
        _, raw = self.state(); integrity = self.root / "g5-integrity.json"; write_json(integrity, {"status": "PASS", "candidate_fingerprint": candidate, "ledger_hash": ledger.sha256_bytes(raw)})
        before = self.paths["ledger"].read_bytes()
        rejected = self.call("import-manual", "--control-root", str(self.control), "--run-id", self.run_id, "--owner-token", self.token, "--revision", str(self.expected_revision), "--attempt-id", attempt_id, "--return-file", str(stale_path), "--environment-receipt", str(env_path), "--context-receipt", str(context_path), "--integrity-receipt", str(integrity), "--intent-revision", "2", "--candidate-fingerprint", candidate, "--required-criteria", "C-1,C-2", expect=2)
        if "candidate fingerprint mismatch" not in str(rejected) or self.paths["ledger"].read_bytes() != before:
            raise AssertionError("stale G5 return changed authority")
        return_path = inbox_root / "acceptance.json"; write_json(return_path, base_return)
        self.mutate("import-g5-pass", "import-manual", "--control-root", str(self.control), "--run-id", self.run_id, "--owner-token", self.token, "--revision", str(self.expected_revision), "--attempt-id", attempt_id, "--return-file", str(return_path), "--environment-receipt", str(env_path), "--context-receipt", str(context_path), "--integrity-receipt", str(integrity), "--intent-revision", "2", "--candidate-fingerprint", candidate, "--required-criteria", "C-1,C-2")
        self.idempotent("import-g5-pass-lost-response", "import-manual", "--control-root", str(self.control), "--run-id", self.run_id, "--owner-token", self.token, "--revision", str(self.expected_revision - 1), "--attempt-id", attempt_id, "--return-file", str(return_path), "--environment-receipt", str(env_path), "--context-receipt", str(context_path), "--integrity-receipt", str(integrity), "--intent-revision", "2", "--candidate-fingerprint", candidate, "--required-criteria", "C-1,C-2")
        self.mutate("g6-accepted", "gate", "--control-root", str(self.control), "--run-id", self.run_id, "--owner-token", self.token, "--revision", str(self.expected_revision), "--phase", "ACCEPT", "--control", "ACCEPTED", "--gate-id", "G6", "--reason", "g6_pass", "--next-action", "terminal_accepted")

    def run(self) -> dict[str, object]:
        self.bootstrap(); self.design_cycle(); _, final_candidate = self.execute(); self.accept(final_candidate)
        state, raw = self.state()
        if (state["lifecycle"]["phase"], state["lifecycle"]["control"]) != ("ACCEPT", "ACCEPTED"):
            raise AssertionError("qualification did not reach terminal ACCEPTED")
        if any(item.get("lease", {}).get("state") in ("active", "quarantined") for item in state.get("attempts", [])):
            raise AssertionError("terminal run retains an active/quarantined lease")
        if any(item.get("state") in ("prepared", "uncertain") for item in state.get("operations", [])):
            raise AssertionError("terminal run retains an unresolved operation")
        return {"qualified": True, "release": ledger.SKILL_VERSION, "run_id": self.run_id, "terminal": {"phase": "ACCEPT", "control": "ACCEPTED", "revision": state["revision"], "ledger_hash": ledger.sha256_bytes(raw)}, "design_history": [{"id": item["id"], "status": item["status"], "published_revision": item["published_revision"]} for item in state["design_publication_history"]], "requirements_publication": state["requirements_publications"][0], "acceptance_rounds": state["acceptance"], "events": self.events}


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="codex-autopilot-v104-") as directory:
        result = Qualification(Path(directory)).run()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
