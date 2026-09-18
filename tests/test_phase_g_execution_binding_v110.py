from __future__ import annotations

import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tools import ledger
from tests.test_phase_b_projections_v110 import (
    OWNER,
    RUN_ID,
    TICKET_ID,
    init_run,
    install_execution_design,
    run,
    seed_ready_ticket,
    worker_packet,
    write_json,
)


ROOT = Path(__file__).resolve().parents[1]
CLI = ["python3", str(ROOT / "tools" / "ledger.py")]


def fixture_route(route_id: str) -> dict[str, Any]:
    return {
        "id": route_id, "capability": "fixture-worker", "reasoning": "synthetic bounded execution",
        "requested_binding": "fixture-model", "observed_binding": "fixture-model",
        "adequacy": "CONFIRMED", "context_grade": "PACKET_SCOPED",
    }


def install_current_execution_authority(
    paths: dict[str, Path], repo: Path, *, route_records: list[dict[str, Any]] | None = None,
) -> None:
    """Upgrade a synthetic current-writer run to a published, executable mandate."""
    state, previous = ledger.load_state(paths)
    intent_path = paths["run"] / "fixture-intent.md"
    design_path = paths["run"] / "fixture-design.md"
    intent_path.write_text("# Fixture intent\n", encoding="utf-8")
    design_path.write_text("# Fixture design\n", encoding="utf-8")
    intent_hash = ledger.sha256_file(intent_path)
    design_hash = ledger.sha256_file(design_path)
    ticket_refs = [item["id"] for item in state.get("tickets", [])]
    for ticket in state.get("tickets", []):
        ticket["criterion_refs"] = ["C-1"]
        ticket["contract_refs"] = ["K-1"]
    state["documents"] = [
        {"id": "D-intent", "version": "v1", "path": str(intent_path), "hash": intent_hash, "kind": "intent", "section_anchors": []},
        {"id": "D-design", "version": "v1", "path": str(design_path), "hash": design_hash, "kind": "design", "section_anchors": []},
    ]
    state["intent"] = {"current_revision": "intent-v1", "document_ref": "D-intent", "document_hash": intent_hash, "approved_amendments": []}
    state["requirements"] = [{"id": "REQ-fixture", "version": "v1", "status": "active", "provenance_refs": ["D-intent"], "criterion_refs": ["C-1"]}]
    state["criteria"] = [{"id": "C-1", "version": "v1", "requirement_refs": ["REQ-fixture"], "oracle": "fixture execution oracle", "status": "active", "source_ref": "D-intent"}]
    state["contracts"] = [{
        "id": "K-1", "version": "v1", "status": "active", "provenance_refs": ["D-intent"],
        "producer_refs": [], "consumer_refs": ticket_refs, "implementation_availability": "available",
        "implementation_availability_evidence_refs": ["fixture:K-1-available"],
    }]
    state["repository"]["execution_root"] = str(repo)
    state["repository"]["checkout"] = str(repo)
    state["repository"]["initial_head"] = "a" * 40
    routes = route_records or []
    state["routes"] = copy.deepcopy(routes)
    route_raw = ledger.canonical_bytes(routes)
    bundle_raw = ledger.canonical_bytes({
        "fixture": "current-writer execution authority", "intent_hash": intent_hash,
        "design_hash": design_hash, "ticket_refs": ticket_refs, "route_hash": ledger.sha256_bytes(route_raw),
    })
    bundle_hash = ledger.sha256_bytes(bundle_raw)
    ledger.object_store(paths, bundle_raw)
    publication = {
        "id": "B-execution-authority", "version": "v1", "status": "PUBLISHED",
        "owner_epoch": state["owner"]["epoch"], "intent_revision": "intent-v1",
        "intent_document_ref": "D-intent", "intent_document_hash": intent_hash,
        "publication_hash": bundle_hash, "bundle_ref": f"objects/{bundle_hash}",
        "published_revision": state["revision"], "document_refs": ["D-design"],
        "requirement_refs": ["REQ-fixture"], "criterion_refs": ["C-1"],
        "requirements_publication_ref": None, "contract_refs": ["K-1"],
        "ticket_refs": ticket_refs, "route_refs": [item["id"] for item in routes], "invalidated_by": [],
    }
    state["design_publication"] = publication
    state["design_publication_history"] = [copy.deepcopy(publication)]
    state["previous_publication_hash"] = ledger.sha256_bytes(previous)
    ledger.validate_ledger(state)
    ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))


def publish_fixture_route(paths: dict[str, Path], route: dict[str, Any]) -> dict[str, Any]:
    """Append a route and a new design-publication snapshot for a synthetic dispatch."""
    route_record = copy.deepcopy(route)
    route_id = route_record.get("id")
    if not isinstance(route_id, str):
        raise AssertionError("fixture route requires a stable id")
    state, previous = ledger.load_state(paths)
    existing = next((item for item in state.get("routes", []) if item.get("id") == route_id), None)
    if existing is not None:
        if existing != route_record:
            raise AssertionError(f"fixture route ID collision: {route_id}")
        return state["design_publication"]
    state.setdefault("routes", []).append(route_record)
    prior = state["design_publication"]
    route_refs = sorted(set(prior.get("route_refs", [])) | {route_id})
    latest_revision = state.get("revision", 0)
    pub_id = f"B-execution-authority-{len(state.get('design_publication_history', [])) + 1}"
    bundle_raw = ledger.canonical_bytes({
        "fixture": "current-writer execution authority route update",
        "previous_publication_hash": prior["publication_hash"],
        "route_refs": route_refs,
        "routes": sorted(state["routes"], key=lambda item: item["id"]),
    })
    bundle_hash = ledger.sha256_bytes(bundle_raw)
    ledger.object_store(paths, bundle_raw)
    publication = {
        **copy.deepcopy(prior), "id": pub_id, "publication_hash": bundle_hash,
        "bundle_ref": f"objects/{bundle_hash}", "published_revision": latest_revision,
        "route_refs": route_refs,
    }
    state.setdefault("design_publication_history", []).append(copy.deepcopy(publication))
    state["design_publication"] = publication
    state["previous_publication_hash"] = ledger.sha256_bytes(previous)
    ledger.validate_ledger(state)
    ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
    return publication


def bind_worker_packet(state: dict[str, Any], ticket: dict[str, Any], packet: dict[str, Any]) -> None:
    intent = ledger.current_intent_binding(state)
    publication = state["design_publication"]
    packet["identity"].update({
        "run_id": state["run_id"], "ticket_id": ticket["id"],
        "attempt_id": packet["identity"]["attempt_id"], "epoch": state["owner"]["epoch"],
        "intent_revision": intent["revision"], "intent_document_ref": intent["document_ref"],
        "intent_document_hash": intent["document_hash"],
        "design_publication_ref": publication["id"],
        "design_publication_hash": publication["publication_hash"],
        "design_publication_revision": publication["published_revision"],
        "contract_refs": sorted(ticket.get("contract_refs", [])),
    })
    packet.update({
        "intent_revision": intent["revision"], "intent_document_ref": intent["document_ref"],
        "intent_document_hash": intent["document_hash"],
    })
    candidate = ledger.current_candidate_record(state, ticket)
    packet.setdefault("workspace", {})["root"] = state["repository"].get("execution_root") or ticket.get("checkout") or packet["workspace"].get("root")
    packet["workspace"]["expected_base"] = candidate["sha"] if candidate else state["repository"].get("initial_head")


class PhaseGExecutionBindingTests(unittest.TestCase):
    def setup_dispatch(self, root: Path) -> tuple[Path, Path, dict[str, Path], Path, dict[str, Any]]:
        control, repo, paths = init_run(root)
        seed_ready_ticket(paths, repo)
        install_execution_design(paths, repo)
        state, _ = ledger.load_state(paths)
        packet_path = worker_packet(root, repo, "A-G")
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        return control, repo, paths, packet_path, packet

    def dispatch(
        self, control: Path, packet_path: Path, revision: int, *, expect: int = 0,
        attempt_id: str = "A-G",
    ) -> subprocess.CompletedProcess[str]:
        return run(
            "dispatch", "--control-root", str(control), "--run-id", RUN_ID,
            "--owner-token", OWNER, "--revision", str(revision), "--ticket-id", TICKET_ID,
            "--attempt-id", attempt_id, "--lease-id", f"L-{attempt_id}",
            "--route-id", "route-G", "--packet", str(packet_path), expect=expect,
        )

    def test_dispatch_persists_full_execution_binding_and_replay_rechecks_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, _, paths, packet_path, packet = self.setup_dispatch(root)
            self.dispatch(control, packet_path, revision=1)
            state, _ = ledger.load_state(paths)
            attempt = ledger.attempt_by_id(state, "A-G")
            binding = attempt["execution_binding"]
            self.assertEqual(TICKET_ID, binding["ticket_id"])
            self.assertEqual(packet["identity"]["design_publication_hash"], binding["design_publication_hash"])
            self.assertEqual(["C-1"], binding["criterion_refs"])
            self.assertEqual([], binding["contract_bindings"])
            self.assertEqual(
                ledger.sha256_bytes(ledger.canonical_bytes(binding)),
                attempt["execution_binding_hash"],
            )

            replay = self.dispatch(control, packet_path, revision=1)
            self.assertTrue(json.loads(replay.stdout)["idempotent"])

            attempt["execution_binding_hash"] = "f" * 64
            ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
            before = paths["ledger"].read_bytes()
            rejected = self.dispatch(control, packet_path, revision=1, expect=2)
            self.assertIn("binding", rejected.stderr.lower())
            self.assertEqual(before, paths["ledger"].read_bytes())

    def test_validate_ledger_rejects_cross_record_execution_binding_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            control, _, paths, packet_path, _ = self.setup_dispatch(Path(directory))
            self.dispatch(control, packet_path, revision=1)
            baseline, _ = ledger.load_state(paths)
            cases = {
                "binding hash": lambda attempt: attempt.__setitem__("execution_binding_hash", "f" * 64),
                "run": lambda attempt: attempt["execution_binding"].update({"run_id": "other-run"}),
                "ticket": lambda attempt: attempt["execution_binding"].update({"ticket_id": "T-other"}),
                "attempt": lambda attempt: attempt["execution_binding"].update({"attempt_id": "A-other"}),
                "kind": lambda attempt: attempt["execution_binding"].update({"kind": "review"}),
                "mode": lambda attempt: attempt["execution_binding"].update({"mode": "repair"}),
                "epoch": lambda attempt: attempt["execution_binding"].update({"epoch": 1}),
                "packet": lambda attempt: attempt["execution_binding"].update({"packet_hash": "0" * 64}),
                "base": lambda attempt: attempt["execution_binding"].update({"base_sha": "b" * 40}),
                "route": lambda attempt: attempt["execution_binding"].update({"route_id": "route-other"}),
                "published design": lambda attempt: attempt["execution_binding"].update({"design_publication_hash": "f" * 64}),
                "intent document": lambda attempt: attempt["execution_binding"].update({"intent_document_ref": "D-missing"}),
            }
            for label, mutate in cases.items():
                with self.subTest(case=label):
                    corrupted = copy.deepcopy(baseline)
                    attempt = ledger.attempt_by_id(corrupted, "A-G")
                    mutate(attempt)
                    if label != "binding hash":
                        attempt["execution_binding_hash"] = ledger.sha256_bytes(ledger.canonical_bytes(attempt["execution_binding"]))
                    with self.assertRaises(ledger.LedgerError):
                        ledger.validate_ledger(corrupted)

    def test_dispatch_rejects_incomplete_or_stale_current_authority_without_publication(self) -> None:
        mutations = {
            "omitted intent": lambda packet: packet.pop("intent_document_hash"),
            "stale design": lambda packet: packet["identity"].update({"design_publication_hash": "f" * 64}),
            "stale base": lambda packet: packet["workspace"].update({"expected_base": "b" * 40}),
            "criteria downgrade": lambda packet: packet["acceptance"].__setitem__(0, {"criterion_id": "C-2"}),
            "deny wins": lambda packet: packet["write"].update({"deny": ["app.txt"]}),
        }
        for label, mutate in mutations.items():
            with self.subTest(case=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                control, _, paths, original_path, packet = self.setup_dispatch(root)
                mutate(packet)
                bad_path = root / "mutated-packet.json"
                write_json(bad_path, packet)
                before = paths["ledger"].read_bytes()
                rejected = self.dispatch(control, bad_path, revision=1, expect=2)
                self.assertNotEqual(0, rejected.returncode)
                self.assertEqual(before, paths["ledger"].read_bytes())

    def test_packet_contract_coverage_is_authoritative(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, _, paths, packet_path, packet = self.setup_dispatch(root)
            state, _ = ledger.load_state(paths)
            state["contracts"] = [{
                "id": "K-1", "version": "v4", "status": "active", "provenance_refs": ["D-intent"],
                "producer_refs": [], "consumer_refs": [TICKET_ID],
                "implementation_availability": "available",
                "implementation_availability_evidence_refs": ["fixture:available"],
            }]
            state["tickets"][0]["contract_refs"] = ["K-1"]
            publication = state["design_publication"]
            # First prove that a ticket cannot introduce a contract outside the
            # currently published design, even if the packet repeats that ref.
            packet["identity"]["contract_refs"] = ["K-1"]
            ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
            outside_publication = root / "outside-publication.json"
            write_json(outside_publication, packet)
            before = paths["ledger"].read_bytes()
            rejected = self.dispatch(control, outside_publication, revision=1, expect=2)
            self.assertIn("design publication", rejected.stderr)
            self.assertEqual(before, paths["ledger"].read_bytes())

            # Publish a bundle whose authoritative contract refs include K-1.
            bundle_raw = ledger.canonical_bytes({"fixture": "Phase B execution binding", "contract_refs": ["K-1"]})
            bundle_hash = ledger.sha256_bytes(bundle_raw)
            ledger.object_store(paths, bundle_raw)
            publication["contract_refs"] = ["K-1"]
            publication["publication_hash"] = bundle_hash
            publication["bundle_ref"] = f"objects/{bundle_hash}"
            state["design_publication_history"][-1] = copy.deepcopy(publication)
            ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
            packet["identity"]["design_publication_hash"] = bundle_hash

            packet["identity"]["contract_refs"] = []
            omitted = root / "omitted-contract.json"
            write_json(omitted, packet)
            before = paths["ledger"].read_bytes()
            rejected = self.dispatch(control, omitted, revision=1, expect=2)
            self.assertIn("contract_refs", rejected.stderr)
            self.assertEqual(before, paths["ledger"].read_bytes())

            packet["identity"]["contract_refs"] = ["K-1"]
            packet["workspace"]["expected_base"] = state["repository"]["initial_head"]
            correctly_bound = root / "correct-contract.json"
            write_json(correctly_bound, packet)
            self.dispatch(control, correctly_bound, revision=1)
            dispatched, _ = ledger.load_state(paths)
            attempt = ledger.attempt_by_id(dispatched, "A-G")
            self.assertEqual(
                [{"ref": "K-1", "version": "v4", "role": "implementation_input",
                  "implementation_availability": "available", "evidence_refs": ["fixture:available"]}],
                attempt["execution_binding"]["contract_bindings"],
            )

    def test_ingest_requires_registered_kind_and_exact_return_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, _, paths, packet_path, packet = self.setup_dispatch(root)
            self.dispatch(control, packet_path, revision=1)
            state, _ = ledger.load_state(paths)
            attempt = ledger.attempt_by_id(state, "A-G")
            returned = {
                "identity": {
                    **copy.deepcopy(packet["identity"]), "packet_hash": attempt["packet_hash"],
                },
                "status": "BLOCKED", "result": "fixture stopped safely", "files": [],
                "checks": [{"check_id": "oracle", "outcome": "fail", "actual": "blocked", "evidence_ref": "EV-G"}],
                "criteria": [{"criterion_id": "C-1", "outcome": "unverifiable", "evidence_refs": ["EV-G"]}],
                "issues": [{"cause": "environment", "impact": "blocking", "affected_refs": [TICKET_ID], "actual": "fixture block"}],
            }
            inbox = paths["scratch"] / "A-G" / "return.json"
            write_json(inbox, returned)
            before = paths["ledger"].read_bytes()
            wrong_kind = run(
                "ingest-return", "--control-root", str(control), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", "2", "--attempt-id", "A-G",
                "--return-file", str(inbox), "--kind", "review", expect=2,
            )
            self.assertIn("kind", wrong_kind.stderr.lower())
            self.assertEqual(before, paths["ledger"].read_bytes())

            del returned["identity"]["design_publication_hash"]
            write_json(inbox, returned)
            stale = run(
                "ingest-return", "--control-root", str(control), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", "2", "--attempt-id", "A-G",
                "--return-file", str(inbox), "--kind", "worker", expect=2,
            )
            self.assertIn("binding", stale.stderr.lower())
            self.assertEqual(before, paths["ledger"].read_bytes())

            returned["identity"]["design_publication_hash"] = packet["identity"]["design_publication_hash"]
            write_json(inbox, returned)
            run(
                "ingest-return", "--control-root", str(control), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", "2", "--attempt-id", "A-G",
                "--return-file", str(inbox), "--kind", "worker",
            )
            ingested, _ = ledger.load_state(paths)
            ingested_attempt = ledger.attempt_by_id(ingested, "A-G")
            ingested_attempt["execution_binding_hash"] = "f" * 64
            ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(ingested))
            before = paths["ledger"].read_bytes()
            replay = run(
                "ingest-return", "--control-root", str(control), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", "3", "--attempt-id", "A-G",
                "--return-file", str(inbox), "--kind", "worker", expect=2,
            )
            self.assertIn("binding", replay.stderr.lower())
            self.assertEqual(before, paths["ledger"].read_bytes())


if __name__ == "__main__":
    unittest.main()
