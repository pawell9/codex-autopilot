from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tools import ledger
from tests import test_phase_g_execution_binding_v110 as phase_g_fixture
from tests.test_phase_b_projections_v110 import OWNER, RUN_ID, TICKET_ID, run, write_json


ROOT = Path(__file__).resolve().parents[1]


def record_runtime_event(
    control: Path, run_id: str, owner_token: str, paths: dict[str, Path], attempt_id: str,
    event: str, event_id: str, *, instance: str | None = "runtime-test",
    descendant_writers: str = "not_applicable",
) -> dict[str, Any]:
    """Publish an exact runtime receipt through the same public CLI used by adapters."""
    state, _ = ledger.load_state(paths)
    attempt = ledger.attempt_by_id(state, attempt_id)
    receipt = {
        "kind": "runtime_observation", "event_id": event_id, "event": event,
        "run_id": run_id, "attempt_id": attempt_id, "epoch": attempt["epoch"],
        "packet_hash": attempt["packet_hash"], "spawn_request_id": attempt["runtime"]["spawn_request_id"],
        "runtime_instance_id": instance, "observed_at": "2026-09-18T12:00:00Z",
        "observer": "runtime-adapter-test", "runtime_build": "fixture-1", "return_hash": None,
        "coverage": {"scope": "test process tree", "descendant_writers": descendant_writers},
    }
    event_path = paths["run"] / f"{event_id}.json"
    write_json(event_path, receipt)
    run(
        "observe-runtime", "--control-root", str(control), "--run-id", run_id,
        "--owner-token", owner_token, "--revision", str(state["revision"]),
        "--attempt-id", attempt_id, "--event", event, "--event-id", event_id,
        "--event-file", str(event_path),
    )
    return receipt


class PhaseGRuntimeObservationTests(unittest.TestCase):
    def setUp_dispatch(self, root: Path) -> tuple[phase_g_fixture.PhaseGExecutionBindingTests, Path, dict[str, Path], Path, dict[str, Any]]:
        fixture = phase_g_fixture.PhaseGExecutionBindingTests()
        control, _, paths, packet_path, packet = fixture.setup_dispatch(root)
        fixture.dispatch(control, packet_path, revision=1)
        return fixture, control, paths, packet_path, packet

    def observe(
        self, root: Path, control: Path, paths: dict[str, Path], attempt_id: str,
        event: str, revision: int, *, event_id: str, instance: str | None = "runtime-1",
        descendant_writers: str = "not_applicable", return_hash: str | None = None, expect: int = 0,
    ) -> subprocess.CompletedProcess[str]:
        state, _ = ledger.load_state(paths)
        attempt = ledger.attempt_by_id(state, attempt_id)
        receipt = {
            "kind": "runtime_observation", "event_id": event_id, "event": event,
            "run_id": RUN_ID, "attempt_id": attempt_id, "epoch": attempt["epoch"],
            "packet_hash": attempt["packet_hash"], "spawn_request_id": attempt["runtime"]["spawn_request_id"],
            "runtime_instance_id": instance, "observed_at": "2026-09-18T12:00:00Z",
            "observer": "runtime-adapter-test", "runtime_build": "fixture-1",
            "return_hash": return_hash,
            "coverage": {"scope": "test process tree", "descendant_writers": descendant_writers},
        }
        event_path = root / f"{event_id}.json"
        write_json(event_path, receipt)
        return run(
            "observe-runtime", "--control-root", str(control), "--run-id", RUN_ID,
            "--owner-token", OWNER, "--revision", str(revision), "--attempt-id", attempt_id,
            "--event", event, "--event-id", event_id, "--event-file", str(event_path), expect=expect,
        )

    def test_registration_and_dispatch_replay_do_not_count_as_spawns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = phase_g_fixture.PhaseGExecutionBindingTests()
            control, _, paths, packet_path, _ = fixture.setup_dispatch(root)
            prepared = fixture.dispatch(control, packet_path, revision=1)
            first = json.loads(prepared.stdout)
            self.assertEqual("register_only_use_spawn_request_id_once", first["spawn_disposition"])
            self.assertTrue(first["spawn_request_id"].startswith("spawn-"))
            replay = fixture.dispatch(control, packet_path, revision=1)
            self.assertEqual("existing_request_do_not_spawn_again", json.loads(replay.stdout)["spawn_disposition"])
            state, _ = ledger.load_state(paths)
            self.assertEqual(1, state["usage"]["counters"]["attempt_registrations"])
            self.assertEqual(0, state["usage"]["counters"]["spawn_calls"])
            attempt = ledger.attempt_by_id(state, "A-G")
            self.assertEqual("unknown", ledger.runtime_liveness(attempt))
            self.assertEqual(
                ledger.stable_spawn_request_id(RUN_ID, "A-G", 0, attempt["packet_hash"]),
                attempt["runtime"]["spawn_request_id"],
            )

            started = self.observe(root, control, paths, "A-G", "start", 2, event_id="OBS-START")
            self.assertEqual("spawn_observed_once; do_not_repeat_spawn", json.loads(started.stdout)["disposition"])
            replay_start = self.observe(root, control, paths, "A-G", "start", 2, event_id="OBS-START")
            self.assertTrue(json.loads(replay_start.stdout)["idempotent"])
            run(
                "gate", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
                "--revision", "3", "--phase", "EXECUTE", "--control", "ACTIVE",
                "--next-action", "runtime_replay_fixture_progress",
            )
            revision_after_progress = ledger.load_state(paths)[0]["revision"]
            replay_after_progress = self.observe(root, control, paths, "A-G", "start", 2, event_id="OBS-START")
            self.assertTrue(json.loads(replay_after_progress.stdout)["idempotent"])
            self.assertEqual(revision_after_progress, json.loads(replay_after_progress.stdout)["revision"])
            replay_dispatch = fixture.dispatch(control, packet_path, revision=1)
            self.assertEqual("existing_request_do_not_spawn_again", json.loads(replay_dispatch.stdout)["spawn_disposition"])
            state, _ = ledger.load_state(paths)
            self.assertEqual(1, state["usage"]["counters"]["spawn_calls"])
            self.assertEqual("running", ledger.runtime_liveness(ledger.attempt_by_id(state, "A-G")))

    def test_return_observation_is_not_stop_and_stop_must_cover_descendants(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, control, paths, packet_path, packet = self.setUp_dispatch(root)
            self.observe(root, control, paths, "A-G", "start", 2, event_id="OBS-START")
            state, _ = ledger.load_state(paths)
            attempt = ledger.attempt_by_id(state, "A-G")
            returned = {
                "identity": {**packet["identity"], "packet_hash": attempt["packet_hash"]},
                "status": "DONE", "result": "fixture work complete", "files": [],
                "checks": [{"check_id": "oracle", "outcome": "pass", "actual": "passed", "evidence_ref": "EV-G"}],
                "criteria": [{"criterion_id": "C-1", "outcome": "satisfied", "evidence_refs": ["EV-G"]}],
            }
            inbox = paths["scratch"] / "A-G" / "return.json"
            write_json(inbox, returned)
            return_hash = ledger.sha256_bytes(ledger.canonical_bytes(returned))
            self.observe(root, control, paths, "A-G", "return_observed", 3, event_id="OBS-RETURN", return_hash=return_hash)
            state, _ = ledger.load_state(paths)
            self.assertEqual("running", ledger.runtime_liveness(ledger.attempt_by_id(state, "A-G")))
            run(
                "ingest-return", "--control-root", str(control), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", "4", "--attempt-id", "A-G",
                "--return-file", str(inbox), "--kind", "worker",
            )
            state, _ = ledger.load_state(paths)
            self.assertEqual("running", ledger.runtime_liveness(ledger.attempt_by_id(state, "A-G")))
            blocked = run(
                "candidate", "--control-root", str(control), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", "5", "--attempt-id", "A-G",
                "--operation-id", "OP-CANDIDATE", expect=2,
            )
            self.assertIn("exact runtime stop", blocked.stderr)

            stop_missing_descendants = self.observe(
                root, control, paths, "A-G", "stop", 5, event_id="OBS-STOP-UNKNOWN",
                descendant_writers="unknown", expect=2,
            )
            self.assertNotEqual(0, stop_missing_descendants.returncode)
            accepted_stop = self.observe(
                root, control, paths, "A-G", "stop", 5, event_id="OBS-STOP",
                descendant_writers="included",
            )
            self.assertEqual("stopped", json.loads(accepted_stop.stdout)["liveness"])

    def test_not_started_is_explicit_and_does_not_increment_spawn_count(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = phase_g_fixture.PhaseGExecutionBindingTests()
            control, _, paths, packet_path, _ = fixture.setup_dispatch(root)
            fixture.dispatch(control, packet_path, revision=1)
            result = self.observe(
                root, control, paths, "A-G", "not_started", 2, event_id="OBS-NOT-STARTED", instance=None,
            )
            self.assertEqual("not_started", json.loads(result.stdout)["liveness"])
            state, _ = ledger.load_state(paths)
            self.assertEqual(0, state["usage"]["counters"]["spawn_calls"])
            self.assertEqual("not_started", ledger.runtime_liveness(ledger.attempt_by_id(state, "A-G")))
            rejected_start = self.observe(
                root, control, paths, "A-G", "start", state["revision"], event_id="OBS-START-CONFLICT",
                expect=2,
            )
            self.assertIn("start observation is valid only once", rejected_start.stderr)

    def test_late_stop_after_return_observation_cannot_rebind_instance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, control, paths, _, _ = self.setUp_dispatch(root)
            self.observe(
                root, control, paths, "A-G", "return_observed", 2,
                event_id="OBS-RETURN-UNKNOWN", return_hash="a" * 64,
            )
            state, _ = ledger.load_state(paths)
            attempt = ledger.attempt_by_id(state, "A-G")
            self.assertEqual("unknown", ledger.runtime_liveness(attempt))
            self.assertEqual("runtime-1", attempt["runtime"]["runtime_instance_id"])
            mismatched_stop = self.observe(
                root, control, paths, "A-G", "stop", 3,
                event_id="OBS-STOP-WRONG-INSTANCE", instance="runtime-other",
                descendant_writers="included", expect=2,
            )
            self.assertIn("exact runtime instance already observed", mismatched_stop.stderr)
            accepted_stop = self.observe(
                root, control, paths, "A-G", "stop", 3,
                event_id="OBS-STOP-LATE", instance="runtime-1",
                descendant_writers="included",
            )
            self.assertEqual("stopped", json.loads(accepted_stop.stdout)["liveness"])

    def test_legacy_attempt_without_runtime_record_is_readable_as_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = phase_g_fixture.PhaseGExecutionBindingTests()
            control, _, paths, packet_path, _ = fixture.setup_dispatch(root)
            fixture.dispatch(control, packet_path, revision=1)
            state, _ = ledger.load_state(paths)
            attempt = ledger.attempt_by_id(state, "A-G")
            attempt.pop("runtime")
            ledger.validate_ledger(state)
            ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
            status = json.loads(run(
                "status", "--control-root", str(control), "--run-id", RUN_ID, "--brief",
            ).stdout)
            projected = next(item for item in status["runtime_attempts"] if item["id"] == "A-G")
            self.assertEqual("unknown", projected["liveness"])
            self.assertFalse(projected["protocol_recorded"])
            self.assertNotIn("observation_refs", attempt)

    def test_legacy_unknown_blocks_candidate_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = phase_g_fixture.PhaseGExecutionBindingTests()
            control, _, paths, packet_path, packet = fixture.setup_dispatch(root)
            fixture.dispatch(control, packet_path, revision=1)
            state, _ = ledger.load_state(paths)
            attempt = ledger.attempt_by_id(state, "A-G")
            attempt.pop("runtime")
            ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
            self.assertFalse(ledger.runtime_stop_proven(paths, attempt))

            returned = {
                "identity": {**packet["identity"], "packet_hash": attempt["packet_hash"]},
                "status": "DONE", "result": "legacy return", "files": [],
                "checks": [{"check_id": "oracle", "outcome": "pass", "actual": "passed", "evidence_ref": "EV-G"}],
                "criteria": [{"criterion_id": "C-1", "outcome": "satisfied", "evidence_refs": ["EV-G"]}],
            }
            inbox = paths["scratch"] / "A-G" / "return.json"
            write_json(inbox, returned)
            run(
                "ingest-return", "--control-root", str(control), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", "2", "--attempt-id", "A-G",
                "--return-file", str(inbox), "--kind", "worker",
            )
            before, _ = ledger.load_state(paths)
            with self.assertRaisesRegex(ledger.LedgerError, "exact runtime stop/not_started"):
                ledger.require_runtime_stopped(paths, ledger.attempt_by_id(before, "A-G"), "candidate qualification")
            rejected = run(
                "candidate", "--control-root", str(control), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", str(before["revision"]),
                "--attempt-id", "A-G", "--operation-id", "missing", expect=2,
            )
            self.assertIn("exact runtime stop/not_started", rejected.stderr)
            after, _ = ledger.load_state(paths)
            self.assertEqual(before["revision"], after["revision"])
            self.assertEqual("unknown", ledger.runtime_liveness(ledger.attempt_by_id(after, "A-G")))

    def test_legacy_unknown_cannot_release_reservation_from_termination_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = phase_g_fixture.PhaseGExecutionBindingTests()
            control, _, paths, packet_path, _ = fixture.setup_dispatch(root)
            fixture.dispatch(control, packet_path, revision=1)
            state, _ = ledger.load_state(paths)
            ledger.attempt_by_id(state, "A-G").pop("runtime")
            ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
            evidence = root / "legacy-stop.json"
            write_json(evidence, {"status": "PASS", "writer_stopped": True, "observation": "historical compatibility evidence"})
            before = paths["ledger"].read_bytes()
            rejected = run(
                "terminate-attempt", "--control-root", str(control), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", "2", "--attempt-id", "A-G",
                "--state", "LOST", "--lease-state", "released", "--evidence", str(evidence), expect=2,
            )
            self.assertIn("exact runtime stop/not_started", rejected.stderr)
            self.assertEqual(before, paths["ledger"].read_bytes())
            final, _ = ledger.load_state(paths)
            self.assertEqual("active", ledger.attempt_by_id(final, "A-G")["lease"]["state"])
            self.assertEqual("unknown", ledger.runtime_liveness(ledger.attempt_by_id(final, "A-G")))

    def test_runtime_observation_objects_are_verified_on_load_and_replay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, control, paths, _, _ = self.setUp_dispatch(root)
            start_file = root / "OBS-START.json"
            self.observe(root, control, paths, "A-G", "start", 2, event_id="OBS-START")
            state, _ = ledger.load_state(paths)
            attempt = ledger.attempt_by_id(state, "A-G")
            start_ref = attempt["runtime"]["start_ref"]
            start_object = paths["objects"] / start_ref.split("/")[1]

            start_object.unlink()
            with self.assertRaisesRegex(ledger.LedgerError, "immutable object is unavailable"):
                ledger.load_state(paths)
            replay = run(
                "observe-runtime", "--control-root", str(control), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", "2", "--attempt-id", "A-G",
                "--event", "start", "--event-id", "OBS-START", "--event-file", str(start_file), expect=2,
            )
            self.assertIn("immutable object is unavailable", replay.stderr)

    def test_runtime_observation_hash_schema_identity_and_pointer_are_verified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, control, paths, _, _ = self.setUp_dispatch(root)
            self.observe(root, control, paths, "A-G", "start", 2, event_id="OBS-START")
            heartbeat = record_runtime_event(
                control, RUN_ID, OWNER, paths, "A-G", "heartbeat", "OBS-HEARTBEAT",
                instance="runtime-1",
            )
            state, _ = ledger.load_state(paths)
            attempt = ledger.attempt_by_id(state, "A-G")
            heartbeat_ref = attempt["runtime"]["heartbeat_refs"][0]
            heartbeat_object = paths["objects"] / heartbeat_ref.split("/")[1]

            tampered_state = json.loads(json.dumps(state))
            tampered_object = paths["objects"] / tampered_state["attempts"][0]["runtime"]["start_ref"].split("/")[1]
            ledger.atomic_write(tampered_object, b"tampered")
            with self.assertRaisesRegex(ledger.LedgerError, "hash does not match"):
                ledger.validate_ledger(tampered_state)
            # Restore the content-addressed object before the remaining isolated checks.
            start_receipt = {
                "kind": "runtime_observation", "event_id": "OBS-START", "event": "start",
                "run_id": RUN_ID, "attempt_id": "A-G", "epoch": attempt["epoch"],
                "packet_hash": attempt["packet_hash"], "spawn_request_id": attempt["runtime"]["spawn_request_id"],
                "runtime_instance_id": "runtime-1", "observed_at": "2026-09-18T12:00:00Z",
                "observer": "runtime-adapter-test", "runtime_build": "fixture-1", "return_hash": None,
                "coverage": {"scope": "test process tree", "descendant_writers": "not_applicable"},
            }
            start_raw = ledger.canonical_bytes(start_receipt)
            ledger.atomic_write(tampered_object, start_raw)

            wrong_schema = json.loads(json.dumps(state))
            malformed = dict(heartbeat, unexpected="field")
            malformed_ref = f"objects/{ledger.object_store(paths, ledger.canonical_bytes(malformed))}"
            wrong_schema_attempt = ledger.attempt_by_id(wrong_schema, "A-G")
            wrong_schema_attempt["runtime"]["observation_refs"][1] = malformed_ref
            wrong_schema_attempt["runtime"]["heartbeat_refs"][0] = malformed_ref
            with self.assertRaisesRegex(ledger.LedgerError, "unknown field"):
                ledger.validate_ledger(wrong_schema)

            wrong_identity = json.loads(json.dumps(state))
            foreign = dict(heartbeat, run_id="different-run")
            foreign_ref = f"objects/{ledger.object_store(paths, ledger.canonical_bytes(foreign))}"
            wrong_identity_attempt = ledger.attempt_by_id(wrong_identity, "A-G")
            wrong_identity_attempt["runtime"]["observation_refs"][1] = foreign_ref
            wrong_identity_attempt["runtime"]["heartbeat_refs"][0] = foreign_ref
            with self.assertRaisesRegex(ledger.LedgerError, "identity does not match"):
                ledger.validate_ledger(wrong_identity)

            wrong_pointer = json.loads(json.dumps(state))
            ledger.attempt_by_id(wrong_pointer, "A-G")["runtime"]["start_ref"] = heartbeat_ref
            with self.assertRaisesRegex(ledger.LedgerError, "pointer/event mismatch"):
                ledger.validate_ledger(wrong_pointer)

    def test_duplicate_runtime_event_ids_are_rejected_by_ledger_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, control, paths, _, _ = self.setUp_dispatch(root)
            self.observe(root, control, paths, "A-G", "start", 2, event_id="OBS-START")
            heartbeat = record_runtime_event(
                control, RUN_ID, OWNER, paths, "A-G", "heartbeat", "OBS-HEARTBEAT",
                instance="runtime-1",
            )
            state, _ = ledger.load_state(paths)
            attempt = ledger.attempt_by_id(state, "A-G")
            duplicate = dict(heartbeat, event_id="OBS-START")
            duplicate_ref = f"objects/{ledger.object_store(paths, ledger.canonical_bytes(duplicate))}"
            attempt["runtime"]["observation_refs"].append(duplicate_ref)
            attempt["runtime"]["heartbeat_refs"].append(duplicate_ref)
            with self.assertRaisesRegex(ledger.LedgerError, "duplicate runtime observation event_id"):
                ledger.validate_ledger(state)


if __name__ == "__main__":
    unittest.main()
