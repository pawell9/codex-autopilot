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
