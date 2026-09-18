from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tools import ledger
from tests.test_phase_b_projections_v110 import install_execution_design

try:
    import test_continuation_candidates as continuation_test_helpers
except ImportError:  # Support package-style unittest discovery too.
    from tests import test_continuation_candidates as continuation_test_helpers


ROOT = Path(__file__).resolve().parents[1]
CLI = ["python3", str(ROOT / "tools" / "ledger.py")]
RUN_ID = "phase-d-proof-run"
OWNER = "owner-a"
TICKET_ID = "T-1"
ATTEMPT_ID = "A-1"
OPERATION_ID = "OP-1"
AUTHORITY_REF = "AUTH-CANDIDATE-1"


def invoke(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([*CLI, *args], text=True, capture_output=True)


def run(*args: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
    result = invoke(*args)
    if result.returncode != expect:
        raise AssertionError(f"expected {expect}, got {result.returncode}: {result.stdout}\n{result.stderr}")
    return result


def write_json(path: Path, value: Any) -> None:
    ledger.atomic_write(path, ledger.canonical_bytes(value))


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, text=True, capture_output=True,
    ).stdout.strip()


def object_snapshot(paths: dict[str, Path]) -> dict[str, bytes]:
    objects = paths["objects"]
    if not objects.exists():
        return {}
    return {str(path.relative_to(objects)): path.read_bytes() for path in sorted(objects.iterdir()) if path.is_file()}


class PhaseDCandidateProofTests(unittest.TestCase):
    def prepare_done_candidate(
        self, root: Path, *, parent_drift: bool = False,
        extra_committed_path: bool = False, rename_outside_lease: bool = False,
    ) -> dict[str, Any]:
        root.mkdir(parents=True, exist_ok=True)
        control, repo = root / "control", root / "repo"
        control.mkdir()
        repo.mkdir()
        subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
        (repo / ".gitignore").write_text("ignored.generated\n", encoding="utf-8")
        (repo / "app.txt").write_text("baseline\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", ".gitignore", "app.txt"], check=True)
        subprocess.run([
            "git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
            "commit", "-qm", "baseline",
        ], check=True)
        base_sha = git(repo, "rev-parse", "HEAD")
        run("init", "--control-root", str(control), "--repo-root", str(repo), "--run-id", RUN_ID, "--owner-token", OWNER)
        paths = ledger.paths(control, RUN_ID)
        state, previous = ledger.load_state(paths)
        state["criteria"] = [{
            "id": "C-1", "version": "v1", "requirement_refs": [], "oracle": "focused", "status": "active",
        }]
        state["tickets"] = [{
            "id": TICKET_ID, "goal_ref": "G-1", "criterion_refs": ["C-1"], "contract_refs": [],
            "dependency_refs": [], "state": "READY", "complexity": "bounded", "risk": "routine",
            "zone": [{"path": "app.txt", "operations": ["modify"]}], "current_attempt": None,
            "current_worker_attempt": None, "last_worker_attempt": None, "current_candidate": None,
            "replacement_refs": [],
        }]
        state["lifecycle"] = {
            "phase": "EXECUTE", "control": "ACTIVE", "reason": None, "issue_refs": [], "stop_target": None,
            "next_action": {"kind": "dispatch_ticket", "subject_refs": [TICKET_ID], "preconditions": [], "read_refs": []},
        }
        state["revision"] = 1
        state["previous_publication_hash"] = ledger.sha256_bytes(previous)
        state["repository"].update({"checkout": str(repo), "branch": "main", "initial_head": base_sha})
        ledger.refresh_control_projection(state)
        ledger.validate_ledger(state)
        ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
        install_execution_design(paths, repo)
        state, _ = ledger.load_state(paths)
        state["repository"]["initial_head"] = base_sha
        ledger.validate_ledger(state)
        ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))

        packet = {
            "identity": {"run_id": RUN_ID, "ticket_id": TICKET_ID, "attempt_id": ATTEMPT_ID, "epoch": 0},
            "kind": "worker", "mode": "implement", "goal": "Phase D verified candidate proof regression",
            "acceptance": [{"criterion_id": "C-1"}],
            "workspace": {"root": str(repo), "expected_base": base_sha},
            "write": {"allow": [{"path": "app.txt", "operations": ["modify"]}]},
            "verification": [{"check_id": "focused", "required": True, "scenario": "focused regression"}],
            "risk": {"level": "routine"}, "context": [{"ref": "contracts/worker.md"}],
            "return_target": {"path": "return.json"},
        }
        intent = ledger.current_intent_binding(state)
        publication = state["design_publication"]
        packet["identity"].update({
            "intent_revision": intent["revision"], "intent_document_ref": intent["document_ref"],
            "intent_document_hash": intent["document_hash"], "design_publication_ref": publication["id"],
            "design_publication_hash": publication["publication_hash"],
            "design_publication_revision": publication["published_revision"], "contract_refs": [],
        })
        packet.update({
            "intent_revision": intent["revision"], "intent_document_ref": intent["document_ref"],
            "intent_document_hash": intent["document_hash"],
        })
        packet_path = root / "packet.json"
        write_json(packet_path, packet)
        run(
            "dispatch", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
            "--revision", "1", "--ticket-id", TICKET_ID, "--attempt-id", ATTEMPT_ID,
            "--lease-id", "L-1", "--route-id", "route-1", "--packet", str(packet_path),
        )
        state, _ = ledger.load_state(paths)
        attempt = ledger.attempt_by_id(state, ATTEMPT_ID)
        for event, event_id, revision, descendants in (
            ("start", "OBS-START", state["revision"], "not_applicable"),
            ("stop", "OBS-STOP", state["revision"] + 1, "included"),
        ):
            observation = {
                "kind": "runtime_observation", "event_id": event_id, "event": event,
                "run_id": RUN_ID, "attempt_id": ATTEMPT_ID, "epoch": attempt["epoch"],
                "packet_hash": attempt["packet_hash"], "spawn_request_id": attempt["runtime"]["spawn_request_id"],
                "runtime_instance_id": "runtime-phase-d", "observed_at": "2026-09-18T12:00:00Z",
                "observer": "runtime-adapter-test", "runtime_build": "fixture-1", "return_hash": None,
                "coverage": {"scope": "test process tree", "descendant_writers": descendants},
            }
            observation_path = root / f"{event_id}.json"
            write_json(observation_path, observation)
            run(
                "observe-runtime", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
                "--revision", str(revision), "--attempt-id", ATTEMPT_ID, "--event", event,
                "--event-id", event_id, "--event-file", str(observation_path),
            )
            state, _ = ledger.load_state(paths)
        worker_return = {
            "identity": {
                **packet["identity"], "packet_hash": state["attempts"][0]["packet_hash"],
            },
            "status": "DONE", "result": "focused proof passed",
            "files": [{"path": "app.txt", "operation": "modify"}],
            "checks": [{"check_id": "focused", "outcome": "pass", "actual": "pass", "evidence_ref": "EV-1"}],
            "criteria": [{"criterion_id": "C-1", "outcome": "satisfied", "evidence_refs": ["EV-1"]}],
        }
        return_path = paths["scratch"] / ATTEMPT_ID / "return.json"
        write_json(return_path, worker_return)
        run(
            "ingest-return", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
            "--revision", str(state["revision"]), "--attempt-id", ATTEMPT_ID, "--return-file", str(return_path), "--kind", "worker",
        )
        state, _ = ledger.load_state(paths)
        run(
            "prepare-effect", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
            "--revision", str(state["revision"]), "--operation-id", OPERATION_ID, "--kind", "candidate_commit",
            "--target", str(repo), "--expected-before", base_sha, "--authority-ref", AUTHORITY_REF,
        )

        if parent_drift:
            subprocess.run([
                "git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                "commit", "--allow-empty", "-qm", "unexpected intermediate parent",
            ], check=True)
        if rename_outside_lease:
            (repo / "app.txt").rename(repo / "outside.txt")
            subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
        else:
            (repo / "app.txt").write_text("verified candidate\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "app.txt"], check=True)
        if extra_committed_path:
            (repo / "outside.txt").write_text("not leased\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "outside.txt"], check=True)
        subprocess.run([
            "git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
            "commit", "-qm", "candidate",
        ], check=True)
        candidate_sha = git(repo, "rev-parse", "HEAD")
        tree_sha = git(repo, "rev-parse", "HEAD^{tree}")
        receipt = {
            "status": "PASS", "run_id": RUN_ID, "ticket_id": TICKET_ID, "attempt_id": ATTEMPT_ID,
            "operation_id": OPERATION_ID, "kind": "candidate_commit", "target": str(repo), "checkout": str(repo),
            "expected_before": base_sha, "base_sha": base_sha, "intended_after": candidate_sha,
            "commit_sha": candidate_sha, "tree_sha": tree_sha,
            "authority_ref": AUTHORITY_REF,
        }
        receipt_path = root / "commit-receipt.json"
        write_json(receipt_path, receipt)
        current, _ = ledger.load_state(paths)
        return {
            "root": root, "control": control, "repo": repo, "paths": paths, "base_sha": base_sha,
            "candidate_sha": candidate_sha, "tree_sha": tree_sha, "receipt": receipt,
            "receipt_path": receipt_path, "revision": current["revision"],
        }

    def candidate_args(self, case: dict[str, Any], *, revision: int | None = None, receipt_path: Path | None = None) -> list[str]:
        args = [
            "candidate", "--control-root", str(case["control"]), "--run-id", RUN_ID,
            "--owner-token", OWNER, "--revision", str(case["revision"] if revision is None else revision),
            "--attempt-id", ATTEMPT_ID, "--operation-id", OPERATION_ID,
        ]
        if receipt_path is not None:
            args.extend(["--commit-receipt", str(receipt_path)])
        return args

    def assert_rejected_without_mutation(self, case: dict[str, Any], *args: str) -> subprocess.CompletedProcess[str]:
        paths = case["paths"]
        before = paths["ledger"].read_bytes()
        objects_before = object_snapshot(paths)
        result = run(*args, expect=2)
        self.assertEqual(before, paths["ledger"].read_bytes(), "rejected candidate changed the ledger")
        self.assertEqual(objects_before, object_snapshot(paths), "rejected candidate wrote immutable proof objects")
        state, _ = ledger.load_state(paths)
        attempt = ledger.attempt_by_id(state, ATTEMPT_ID)
        self.assertIsNone(attempt.get("candidate_proof_ref"))
        self.assertEqual("prepared", next(item for item in state["operations"] if item["id"] == OPERATION_ID)["state"])
        return result

    def proof_and_records(self, case: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
        state, _ = ledger.load_state(case["paths"])
        attempt = ledger.attempt_by_id(state, ATTEMPT_ID)
        ticket = next(item for item in state["tickets"] if item["id"] == TICKET_ID)
        candidate = ledger.current_candidate_record(state, ticket)
        operation = next(item for item in state["operations"] if item["id"] == OPERATION_ID)
        refs = {attempt.get("candidate_proof_ref"), candidate.get("proof_ref"), operation.get("proof_ref")}
        self.assertEqual(1, len(refs), "attempt, candidate, and effect must retain the same proof reference")
        proof_ref = refs.pop()
        self.assertIsInstance(proof_ref, str)
        proof = ledger.stored_payload(case["paths"], proof_ref, "verified candidate proof")
        return proof, attempt, candidate, operation

    def test_done_candidate_publishes_shared_hash_bound_proof_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            case = self.prepare_done_candidate(Path(directory))
            result = json.loads(run(*self.candidate_args(case, receipt_path=case["receipt_path"])).stdout)
            self.assertEqual(case["candidate_sha"], result["candidate"])
            proof, attempt, candidate, operation = self.proof_and_records(case)

            self.assertEqual("DONE", proof["quality"])
            self.assertEqual(RUN_ID, proof["run_id"])
            self.assertEqual(TICKET_ID, proof["ticket_id"])
            self.assertEqual(ATTEMPT_ID, proof["attempt_id"])
            self.assertEqual(OPERATION_ID, proof["operation_id"])
            self.assertEqual(case["base_sha"], proof["base_sha"])
            self.assertEqual(case["candidate_sha"], proof["candidate_sha"])
            self.assertEqual(case["tree_sha"], proof["candidate_tree_sha"])
            self.assertEqual(str(case["repo"].resolve()), proof["checkout"])
            self.assertEqual(str(case["repo"].resolve()), proof["target"])
            self.assertEqual(AUTHORITY_REF, proof["authority_ref"])
            self.assertIsNone(proof["parent_candidate_ref"])
            self.assertEqual(attempt["packet_ref"], proof["packet_ref"])
            self.assertEqual(attempt["packet_hash"], proof["packet_hash"])
            self.assertEqual(attempt["return_ref"], proof["return_ref"])
            self.assertEqual(attempt["return_ref"].split("/", 1)[1], ledger.sha256_bytes(
                ledger.canonical_bytes(ledger.stored_payload(case["paths"], proof["return_ref"], "candidate worker return")),
            ))
            self.assertEqual(ATTEMPT_ID, candidate["producer_attempt_ref"])
            self.assertEqual("finalized", operation["state"])
            self.assertEqual(proof["commit_receipt_ref"], operation["receipt_ref"])
            receipt_ref = proof["commit_receipt_ref"]
            self.assertEqual(f"objects/{ledger.sha256_bytes(ledger.canonical_bytes(case['receipt']))}", receipt_ref)
            self.assertEqual(case["receipt"], ledger.stored_payload(case["paths"], receipt_ref, "original commit receipt"))
            audit = ledger.stored_payload(case["paths"], proof["write_set_audit_ref"], "candidate write-set audit")
            self.assertTrue(audit["pass"])
            self.assertEqual(["app.txt"], audit["changed_paths"])
            self.assertEqual(ledger.sha256_bytes(ledger.canonical_bytes(audit)), proof["write_set_audit_hash"])
            self.assertIn("candidate_proof_ref", attempt)
            self.assertIn("proof_ref", candidate)

            state, raw = ledger.load_state(case["paths"])
            replay = json.loads(run(*self.candidate_args(case, revision=state["revision"], receipt_path=case["receipt_path"])).stdout)
            self.assertTrue(replay["idempotent"])
            self.assertEqual(state["revision"], ledger.load_state(case["paths"])[0]["revision"])
            self.assertEqual(raw, case["paths"]["ledger"].read_bytes())

    def test_done_and_continuation_publications_share_the_same_proof_shape_and_refs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.mkdir(parents=True, exist_ok=True)
            ordinary = self.prepare_done_candidate(root / "ordinary")
            run(*self.candidate_args(ordinary, receipt_path=ordinary["receipt_path"]))
            ordinary_proof, ordinary_attempt, ordinary_candidate, ordinary_operation = self.proof_and_records(ordinary)

            continuation_root = root / "continuation"
            continuation_root.mkdir()
            continuation_helper = continuation_test_helpers.BlockedContinuationCandidateTests()
            continuation = continuation_helper.prepare_case(continuation_root)
            continuation_helper.preserve(continuation)
            continuation_state, _ = ledger.load_state(continuation["paths"])
            continuation_attempt = ledger.attempt_by_id(continuation_state, "A-1")
            continuation_candidate = ledger.current_candidate_record(
                continuation_state, next(item for item in continuation_state["tickets"] if item["id"] == "T-1"),
            )
            continuation_operation = next(item for item in continuation_state["operations"] if item["id"] == "OP-CONT-1")
            self.assertEqual(continuation_attempt["candidate_proof_ref"], continuation_candidate["proof_ref"])
            self.assertEqual(continuation_attempt["candidate_proof_ref"], continuation_operation["proof_ref"])
            continuation_proof = ledger.stored_payload(
                continuation["paths"], continuation_attempt["candidate_proof_ref"], "continuation verified candidate proof",
            )

            self.assertEqual(set(ordinary_proof), set(continuation_proof))
            self.assertEqual("DONE", ordinary_proof["quality"])
            self.assertEqual("CONTINUATION", continuation_proof["quality"])
            self.assertEqual("finalized", ordinary_operation["state"])
            self.assertEqual("finalized", continuation_operation["state"])
            self.assertEqual(ordinary_attempt["candidate_proof_ref"], ordinary_candidate["proof_ref"])

    def test_wrong_or_missing_receipt_bindings_and_wrong_parent_reject_without_mutation(self) -> None:
        mutations = {
            "wrong run": lambda receipt, case: receipt.update({"run_id": "other-run"}),
            "wrong ticket": lambda receipt, case: receipt.update({"ticket_id": "T-other"}),
            "wrong attempt": lambda receipt, case: receipt.update({"attempt_id": "A-other"}),
            "wrong operation": lambda receipt, case: receipt.update({"operation_id": "OP-other"}),
            "wrong kind": lambda receipt, case: receipt.update({"kind": "other_effect"}),
            "wrong target": lambda receipt, case: receipt.update({"target": str(case["root"])}),
            "wrong expected-before": lambda receipt, case: receipt.update({"expected_before": "a" * 40}),
            "wrong intended-after": lambda receipt, case: receipt.update({"intended_after": "b" * 40}),
            "wrong checkout": lambda receipt, case: receipt.update({"checkout": str(case["root"])}),
            "missing checkout": lambda receipt, case: receipt.pop("checkout"),
            "wrong base": lambda receipt, case: receipt.update({"base_sha": "a" * 40}),
            "missing base": lambda receipt, case: receipt.pop("base_sha"),
            "wrong authority": lambda receipt, case: receipt.update({"authority_ref": "AUTH-OTHER"}),
            "missing authority": lambda receipt, case: receipt.pop("authority_ref"),
        }
        for label, mutate in mutations.items():
            with self.subTest(binding=label), tempfile.TemporaryDirectory() as directory:
                case = self.prepare_done_candidate(Path(directory))
                receipt = dict(case["receipt"])
                mutate(receipt, case)
                write_json(case["receipt_path"], receipt)
                self.assert_rejected_without_mutation(case, *self.candidate_args(case, receipt_path=case["receipt_path"]))

        with tempfile.TemporaryDirectory() as directory:
            case = self.prepare_done_candidate(Path(directory), parent_drift=True)
            result = self.assert_rejected_without_mutation(case, *self.candidate_args(case, receipt_path=case["receipt_path"]))
            self.assertRegex(result.stderr.lower(), r"parent|base|proof")

    def test_full_write_set_audit_rejects_unleased_committed_rename_and_ignored_changes(self) -> None:
        for anomaly in ("extra committed path", "rename outside lease", "ignored untracked path"):
            with self.subTest(anomaly=anomaly), tempfile.TemporaryDirectory() as directory:
                case = self.prepare_done_candidate(
                    Path(directory), extra_committed_path=(anomaly == "extra committed path"),
                    rename_outside_lease=(anomaly == "rename outside lease"),
                )
                if anomaly == "ignored untracked path":
                    (case["repo"] / "ignored.generated").write_text("ignored but still outside the audited lease\n", encoding="utf-8")
                result = self.assert_rejected_without_mutation(
                    case, *self.candidate_args(case, receipt_path=case["receipt_path"]),
                )
                self.assertRegex(result.stderr.lower(), r"audit|write|clean|checkout|path")

    def test_applied_effect_is_adopted_once_and_replay_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            case = self.prepare_done_candidate(Path(directory))
            state, _ = ledger.load_state(case["paths"])
            reconcile = {
                **case["receipt"],
                "operation_id": OPERATION_ID,
                "kind": "candidate_commit",
                "target": str(case["repo"]),
                "expected_before": case["base_sha"],
                "intended_after": case["candidate_sha"],
            }
            receipt_path = case["root"] / "effect-receipt.json"
            write_json(receipt_path, reconcile)
            run(
                "reconcile-effect", "--control-root", str(case["control"]), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", str(state["revision"]), "--operation-id", OPERATION_ID,
                "--result", "applied", "--receipt", str(receipt_path),
            )
            applied_state, _ = ledger.load_state(case["paths"])
            self.assertEqual("applied", next(item for item in applied_state["operations"] if item["id"] == OPERATION_ID)["state"])

            adopted = json.loads(run(*self.candidate_args(case, revision=applied_state["revision"])).stdout)
            self.assertFalse(adopted["idempotent"])
            proof, _, _, operation = self.proof_and_records(case)
            self.assertEqual("finalized", operation["state"])
            self.assertEqual(case["candidate_sha"], proof["candidate_sha"])
            self.assertEqual(f"objects/{ledger.sha256_bytes(receipt_path.read_bytes())}", proof["commit_receipt_ref"])

            final_state, final_raw = ledger.load_state(case["paths"])
            replay = json.loads(run(*self.candidate_args(case, revision=final_state["revision"])).stdout)
            self.assertTrue(replay["idempotent"])
            self.assertEqual(final_state["revision"], ledger.load_state(case["paths"])[0]["revision"])
            self.assertEqual(final_raw, case["paths"]["ledger"].read_bytes())

    def test_finalized_candidate_cross_state_links_are_inseparable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            case = self.prepare_done_candidate(Path(directory))
            run(*self.candidate_args(case, receipt_path=case["receipt_path"]))
            state, _ = ledger.load_state(case["paths"])

            mutations = {
                "candidate proof drift": lambda value: value["candidates"][0].update({"proof_ref": f"objects/{'0' * 64}"}),
                "operation loses proof": lambda value: value["operations"][0].update({"proof_ref": None}),
                "operation stops being finalized": lambda value: value["operations"][0].update({"state": "applied"}),
                "finalization revision moves ahead": lambda value: value["operations"][0].update({"finalized_revision": value["revision"] + 1}),
            }
            for label, mutate in mutations.items():
                with self.subTest(link=label):
                    changed = json.loads(json.dumps(state))
                    mutate(changed)
                    with self.assertRaises(ledger.LedgerError):
                        ledger.validate_ledger(changed)

    def test_missing_stored_original_receipt_cannot_be_reconstructed_from_candidate_sha(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            case = self.prepare_done_candidate(Path(directory))
            run(*self.candidate_args(case, receipt_path=case["receipt_path"]))
            proof, _, _, operation = self.proof_and_records(case)
            self.assertEqual("finalized", operation["state"])
            receipt_ref = proof["commit_receipt_ref"]
            object_path = case["paths"]["run"] / receipt_ref
            object_path.unlink()
            revision = json.loads(case["paths"]["ledger"].read_text(encoding="utf-8"))["revision"]
            raw = case["paths"]["ledger"].read_bytes()
            result = run(*self.candidate_args(case, revision=revision, receipt_path=case["receipt_path"]), expect=2)
            self.assertRegex(result.stderr.lower(), r"receipt|object|proof|missing|immutable")
            self.assertEqual(raw, case["paths"]["ledger"].read_bytes())

    def test_missing_stored_write_set_audit_cannot_be_reconstructed_from_worker_return(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            case = self.prepare_done_candidate(Path(directory))
            run(*self.candidate_args(case, receipt_path=case["receipt_path"]))
            proof, _, _, _ = self.proof_and_records(case)
            audit_path = case["paths"]["run"] / proof["write_set_audit_ref"]
            audit_path.unlink()
            revision = json.loads(case["paths"]["ledger"].read_text(encoding="utf-8"))["revision"]
            raw = case["paths"]["ledger"].read_bytes()
            result = run(*self.candidate_args(case, revision=revision, receipt_path=case["receipt_path"]), expect=2)
            self.assertRegex(result.stderr.lower(), r"audit|object|proof|missing|immutable")
            self.assertEqual(raw, case["paths"]["ledger"].read_bytes())


if __name__ == "__main__":
    unittest.main()
