import copy
import json
import subprocess
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

from tools import ledger


ROOT = Path(__file__).resolve().parents[1]
CLI = ["python3", str(ROOT / "tools" / "ledger.py")]


def run(*args: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run([*CLI, *args], text=True, capture_output=True)
    if result.returncode != expect:
        raise AssertionError(f"expected {expect}, got {result.returncode}: {result.stdout}\n{result.stderr}")
    return result


def write_state(paths: dict[str, Path], state: dict) -> None:
    ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))


def tree_bytes(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}


class SemanticWriterFloorTests(unittest.TestCase):
    def initialized(self, root: Path) -> tuple[Path, Path, dict[str, Path]]:
        control, repo = root / "control", root / "repo"
        control.mkdir()
        repo.mkdir()
        run("init", "--control-root", str(control), "--repo-root", str(repo), "--run-id", "semantic-run", "--owner-token", "owner-a")
        return control, repo, ledger.paths(control, "semantic-run")

    def publish_intent(self, root: Path, control: Path, *, revision: int = 0, expect: int = 0) -> subprocess.CompletedProcess[str]:
        source = root / "intent.md"
        source.write_text("# Semantic contract fixture\n", encoding="utf-8")
        return run("publish-intent", "--control-root", str(control), "--run-id", "semantic-run", "--owner-token", "owner-a", "--revision", str(revision), "--intent-file", str(source), "--doc-id", "D-intent", "--doc-version", "v1", "--intent-revision", "v1", expect=expect)

    def gate(self, control: Path, *, expect: int = 0) -> subprocess.CompletedProcess[str]:
        return run("gate", "--control-root", str(control), "--run-id", "semantic-run", "--owner-token", "owner-a", "--revision", "0", "--control", "BLOCKED", "--reason", "fixture", "--next-action", "inspect", expect=expect)

    def test_init_declares_contract_and_writer_floor_then_mutates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, _, paths = self.initialized(root)
            state, _ = ledger.load_state(paths)
            provenance = state["runtime_provenance"]
            self.assertEqual("1.1.1", state["skill_version"])
            self.assertEqual("1.1", provenance["state_contract_version"])
            self.assertEqual("1.1.1", provenance["minimum_writer_version"])
            self.assertIsNone(ledger.mutation_ineligibility(state))
            old_writer_schema = copy.deepcopy(ledger.schema())
            del old_writer_schema["$defs"]["runtime_provenance"]["properties"]["state_contract_version"]
            del old_writer_schema["$defs"]["runtime_provenance"]["properties"]["minimum_writer_version"]
            with self.assertRaisesRegex(ledger.LedgerError, "unknown field"):
                ledger.validate(state, old_writer_schema, old_writer_schema)

            published = json.loads(self.publish_intent(root, control).stdout)
            self.assertEqual(1, published["revision"])
            next_state, _ = ledger.load_state(paths)
            self.assertEqual("1.1", next_state["runtime_provenance"]["state_contract_version"])

    def test_legacy_metadata_is_readable_but_mutation_and_diagnose_are_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, _, paths = self.initialized(root)
            state, _ = ledger.load_state(paths)
            state["runtime_provenance"].pop("state_contract_version")
            state["runtime_provenance"].pop("minimum_writer_version")
            write_state(paths, state)
            before = tree_bytes(paths["run"])

            diagnostic = json.loads(run("diagnose", "--control-root", str(control), "--run-id", "semantic-run").stdout)
            self.assertTrue(diagnostic["readable"])
            self.assertTrue(diagnostic["valid"])
            self.assertFalse(diagnostic["mutation_eligible"])
            self.assertIn("owner-authorized append-only migration", diagnostic["reason"])
            self.assertEqual(before, tree_bytes(paths["run"]))

            rejected = self.publish_intent(root, control, expect=2)
            self.assertIn("mutation is read-only", rejected.stderr)
            self.assertIn("append-only migration", rejected.stderr)
            self.assertEqual(before, tree_bytes(paths["run"]))

            stale_owner = run("publish-intent", "--control-root", str(control), "--run-id", "semantic-run", "--owner-token", "stale-owner", "--revision", "0", "--intent-file", str(root / "intent.md"), "--doc-id", "D-intent", "--doc-version", "v1", "--intent-revision", "v1", expect=2)
            self.assertIn("owner token mismatch", stale_owner.stderr)
            stale_revision = run("publish-intent", "--control-root", str(control), "--run-id", "semantic-run", "--owner-token", "owner-a", "--revision", "1", "--intent-file", str(root / "intent.md"), "--doc-id", "D-intent", "--doc-version", "v1", "--intent-revision", "v1", expect=2)
            self.assertIn("revision mismatch", stale_revision.stderr)
            self.assertEqual(before, tree_bytes(paths["run"]))

    def test_unknown_contract_future_writer_and_malformed_floor_fail_closed(self) -> None:
        cases = (
            ("state_contract_version", "9.9", "not recognized"),
            ("minimum_writer_version", "1.2.0", "requires writer 1.2.0"),
            ("minimum_writer_version", "v1.1.0", "malformed minimum_writer_version"),
        )
        for field, value, message in cases:
            with self.subTest(field=field, value=value), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                control, _, paths = self.initialized(root)
                state, _ = ledger.load_state(paths)
                state["runtime_provenance"][field] = value
                write_state(paths, state)
                before = tree_bytes(paths["run"])
                diagnostic = json.loads(run("diagnose", "--control-root", str(control), "--run-id", "semantic-run").stdout)
                self.assertTrue(diagnostic["readable"])
                self.assertFalse(diagnostic["mutation_eligible"])
                self.assertIn(message, diagnostic["reason"])
                if field == "state_contract_version":
                    run("status", "--control-root", str(control), "--run-id", "semantic-run")
                    run("render-view", "--control-root", str(control), "--run-id", "semantic-run")
                    self.assertEqual(before["ledger.json"], paths["ledger"].read_bytes())
                    before = tree_bytes(paths["run"])
                rejected = self.gate(control, expect=2)
                self.assertIn(message, rejected.stderr)
                self.assertEqual(before, tree_bytes(paths["run"]))

    def test_semver_comparison_is_numeric_and_malformed_versions_do_not_parse(self) -> None:
        self.assertGreater(ledger.semver_tuple("1.10.0"), ledger.semver_tuple("1.9.0"))
        self.assertIsNone(ledger.semver_tuple("1.9"))
        self.assertIsNone(ledger.semver_tuple("01.9.0"))
        self.assertIsNone(ledger.semver_tuple("latest"))

    def test_schema_provenance_mismatch_is_rejected_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, _, paths = self.initialized(root)
            state, _ = ledger.load_state(paths)
            state["runtime_provenance"]["current_schema_version"] = "2.0"
            write_state(paths, state)
            before = tree_bytes(paths["run"])

            diagnostic = json.loads(run("diagnose", "--control-root", str(control), "--run-id", "semantic-run").stdout)
            self.assertFalse(diagnostic["mutation_eligible"])
            self.assertIn("does not match", diagnostic["reason"])
            rejected = self.gate(control, expect=2)
            self.assertIn("does not match", rejected.stderr)
            self.assertEqual(before, tree_bytes(paths["run"]))

    def test_provenance_normalization_does_not_invent_semantic_migration(self) -> None:
        legacy = {"schema_version": ledger.SCHEMA_VERSION, "skill_version": "1.0.0"}
        provenance = ledger.ensure_runtime_provenance(legacy)
        self.assertNotIn("state_contract_version", provenance)
        self.assertNotIn("minimum_writer_version", provenance)

    def test_ineligible_exact_amend_retry_cannot_repair_snapshot_or_write_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, _, paths = self.initialized(root)
            self.publish_intent(root, control)
            source = root / "intent-v2.md"
            source.write_text("# Exact retry fixture\n", encoding="utf-8")
            args = Namespace(
                control_root=str(control), run_id="semantic-run", owner_token="owner-a", revision=1,
                intent_file=str(source), doc_id="D-intent-v2", doc_version="v2",
                intent_revision="v2", amendment_id="AM-1", authority_ref="explicit-user-authority",
            )
            with mock.patch.object(ledger, "write_snapshot", side_effect=OSError("injected snapshot failure")):
                with self.assertRaisesRegex(ledger.LedgerError, "snapshot publication failed"):
                    ledger.cmd_amend(args)

            committed, _ = ledger.load_state(paths)
            self.assertEqual(2, committed["revision"])
            snapshot = ledger.snapshot_path(paths, committed, "amendment")
            self.assertFalse(snapshot.exists())
            committed["runtime_provenance"].pop("state_contract_version")
            committed["runtime_provenance"].pop("minimum_writer_version")
            write_state(paths, committed)
            before = tree_bytes(paths["run"])

            with self.assertRaisesRegex(ledger.LedgerError, "mutation is read-only"):
                ledger.cmd_amend(args)

            self.assertFalse(snapshot.exists())
            self.assertEqual(before, tree_bytes(paths["run"]))


if __name__ == "__main__":
    unittest.main()
