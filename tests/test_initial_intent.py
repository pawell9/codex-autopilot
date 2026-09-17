import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools import ledger


ROOT = Path(__file__).resolve().parents[1]
CLI = ["python3", str(ROOT / "tools" / "ledger.py")]


def run(*args: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run([*CLI, *args], text=True, capture_output=True)
    if result.returncode != expect:
        raise AssertionError(f"expected {expect}, got {result.returncode}: {result.stdout}\n{result.stderr}")
    return result


class InitialIntentTests(unittest.TestCase):
    def init_run(self, root: Path, run_id: str = "run-bootstrap") -> tuple[Path, Path]:
        control, repo = root / "control", root / "repo"
        control.mkdir()
        repo.mkdir()
        run(
            "init",
            "--control-root", str(control),
            "--repo-root", str(repo),
            "--run-id", run_id,
            "--owner-token", "owner-a",
        )
        return control, repo

    def publish(self, control: Path, source: Path, *, revision: int, doc_id: str = "D-intent-v1", expect: int = 0) -> subprocess.CompletedProcess[str]:
        return run(
            "publish-intent",
            "--control-root", str(control),
            "--run-id", "run-bootstrap",
            "--owner-token", "owner-a",
            "--revision", str(revision),
            "--intent-file", str(source),
            "--doc-id", doc_id,
            "--doc-version", "v1",
            "--intent-revision", "intent-v1",
            expect=expect,
        )

    def test_init_publish_validate_amend_and_reject_second_initial_intent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, _ = self.init_run(root)
            paths = ledger.paths(control, "run-bootstrap")
            initial_raw = paths["ledger"].read_bytes()
            source = root / "intent-v1.md"
            source.write_text("# Intent v1\n\nBuild the requested behavior.\n", encoding="utf-8")

            published = json.loads(self.publish(control, source, revision=0).stdout)
            self.assertEqual(1, published["revision"])
            self.assertEqual("INTENT", published["phase"])
            self.assertEqual("ACTIVE", published["control"])
            self.assertEqual("g1_build", published["next_action"]["kind"])

            state, raw = ledger.load_state(paths)
            ledger.validate_ledger(state)
            run("validate", "--file", str(paths["ledger"]), "--kind", "ledger")
            self.assertEqual("1.0.6", state["skill_version"])
            self.assertEqual(1, state["revision"])
            self.assertEqual(ledger.sha256_bytes(initial_raw), state["previous_publication_hash"])
            self.assertEqual(initial_raw, paths["prev"].read_bytes())
            self.assertEqual("intent-v1", state["intent"]["current_revision"])
            self.assertEqual("D-intent-v1", state["intent"]["document_ref"])
            self.assertEqual(ledger.sha256_bytes(source.read_bytes()), state["intent"]["document_hash"])
            self.assertEqual(raw, paths["ledger"].read_bytes())
            canonical = Path(state["documents"][0]["path"])
            self.assertEqual(source.read_bytes(), canonical.read_bytes())

            second = root / "intent-second.md"
            second.write_text("# Accidental second initial intent\n", encoding="utf-8")
            rejected = self.publish(control, second, revision=1, doc_id="D-second", expect=2)
            self.assertIn("initial intent already exists; use amend", rejected.stderr)
            after_reject, after_reject_raw = ledger.load_state(paths)
            self.assertEqual(1, after_reject["revision"])
            self.assertEqual(raw, after_reject_raw)
            self.assertFalse((paths["docs"] / "D-second").exists())

            amended_source = root / "intent-v2.md"
            amended_source.write_text("# Intent v2\n\nBuild the amended behavior.\n", encoding="utf-8")
            amended = run(
                "amend",
                "--control-root", str(control),
                "--run-id", "run-bootstrap",
                "--owner-token", "owner-a",
                "--revision", "1",
                "--intent-file", str(amended_source),
                "--doc-id", "D-intent-v2",
                "--doc-version", "v2",
                "--intent-revision", "intent-v2",
                "--amendment-id", "AM-1",
                "--authority-ref", "user-message-2",
            )
            self.assertEqual(2, json.loads(amended.stdout)["revision"])
            final, _ = ledger.load_state(paths)
            self.assertEqual("intent-v2", final["intent"]["current_revision"])
            self.assertEqual(["AM-1"], final["intent"]["approved_amendments"])
            self.assertEqual("intent-v1", final["invalidations"][0]["previous_intent_revision"])
            self.assertEqual("g1_recheck", final["lifecycle"]["next_action"]["kind"])

    def test_blocked_preflight_and_legacy_ledger_can_publish_initial_intent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, _ = self.init_run(root)
            paths = ledger.paths(control, "run-bootstrap")
            legacy, _ = ledger.load_state(paths)
            legacy["skill_version"] = "1.0.0"
            legacy.pop("runtime_provenance", None)
            legacy.pop("run_settings")
            ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(legacy))
            run(
                "gate",
                "--control-root", str(control),
                "--run-id", "run-bootstrap",
                "--owner-token", "owner-a",
                "--revision", "0",
                "--control", "BLOCKED",
                "--reason", "missing_initial_intent",
                "--next-action", "publish-initial-intent",
            )
            source = root / "intent.md"
            source.write_text("# Recovered initial intent\n", encoding="utf-8")

            published = json.loads(self.publish(control, source, revision=1).stdout)
            self.assertEqual(2, published["revision"])
            self.assertEqual("ACTIVE", published["control"])
            state, _ = ledger.load_state(paths)
            self.assertEqual("1.0.0", state["skill_version"])
            self.assertNotIn("run_settings", state)
            self.assertEqual(ledger.DEFAULT_RUN_SETTINGS, ledger.resolved_run_settings(state))

    def test_invalid_bootstrap_inputs_leave_ledger_and_docs_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, _ = self.init_run(root)
            paths = ledger.paths(control, "run-bootstrap")
            initial_raw = paths["ledger"].read_bytes()
            empty = root / "empty.md"
            empty.write_text(" \n\t", encoding="utf-8")
            rejected = self.publish(control, empty, revision=0, expect=2)
            self.assertIn("non-whitespace Markdown", rejected.stderr)
            self.assertEqual(initial_raw, paths["ledger"].read_bytes())
            self.assertFalse(paths["docs"].exists())

            source = root / "intent.md"
            source.write_text("# Valid intent\n", encoding="utf-8")
            wrong_owner = run(
                "publish-intent",
                "--control-root", str(control),
                "--run-id", "run-bootstrap",
                "--owner-token", "owner-b",
                "--revision", "0",
                "--intent-file", str(source),
                "--doc-id", "D-owner",
                "--doc-version", "v1",
                "--intent-revision", "intent-v1",
                expect=2,
            )
            self.assertIn("owner token mismatch", wrong_owner.stderr)
            self.assertEqual(initial_raw, paths["ledger"].read_bytes())
            self.assertFalse(paths["docs"].exists())

            traversal = self.publish(control, source, revision=0, doc_id="D/../../../escape", expect=2)
            self.assertIn("escapes the run document namespace", traversal.stderr)
            self.assertEqual(initial_raw, paths["ledger"].read_bytes())
            self.assertFalse((root / "escape").exists())

    def test_resume_can_publish_during_recovery_without_bypassing_reconciliation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, _ = self.init_run(root)
            paths = ledger.paths(control, "run-bootstrap")
            run(
                "recover",
                "--control-root", str(control),
                "--run-id", "run-bootstrap",
                "--owner-token", "owner-a",
                "--revision", "0",
                "--reason", "resume_existing_run",
            )
            source = root / "intent.md"
            source.write_text("# Intent restored while resuming\n", encoding="utf-8")

            published = json.loads(self.publish(control, source, revision=1).stdout)
            self.assertEqual(2, published["revision"])
            self.assertEqual("RECOVERING", published["control"])
            self.assertEqual("finish_recovery_then_g1", published["next_action"]["kind"])
            recovering, _ = ledger.load_state(paths)
            self.assertEqual("INTENT", recovering["lifecycle"]["phase"])
            self.assertEqual("RECOVERING", recovering["lifecycle"]["control"])

            run(
                "gate",
                "--control-root", str(control),
                "--run-id", "run-bootstrap",
                "--owner-token", "owner-a",
                "--revision", "2",
                "--phase", "INTENT",
                "--control", "ACTIVE",
                "--next-action", "g1_build",
            )
            resumed, _ = ledger.load_state(paths)
            self.assertEqual("ACTIVE", resumed["lifecycle"]["control"])
            self.assertEqual("g1_build", resumed["lifecycle"]["next_action"]["kind"])

    def test_same_byte_orphan_is_resumable_and_conflicting_orphan_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, _ = self.init_run(root)
            paths = ledger.paths(control, "run-bootstrap")
            source = root / "intent.md"
            source.write_text("# Intent surviving interrupted publication\n", encoding="utf-8")
            destination = ledger.canonical_document_path(paths, "D-intent-v1", "v1")
            ledger.atomic_write(destination, source.read_bytes())

            published = self.publish(control, source, revision=0)
            self.assertEqual(1, json.loads(published.stdout)["revision"])
            state, _ = ledger.load_state(paths)
            self.assertEqual(ledger.sha256_file(destination), state["intent"]["document_hash"])

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, _ = self.init_run(root)
            paths = ledger.paths(control, "run-bootstrap")
            initial_raw = paths["ledger"].read_bytes()
            source = root / "intent.md"
            source.write_text("# Intended bytes\n", encoding="utf-8")
            destination = ledger.canonical_document_path(paths, "D-intent-v1", "v1")
            ledger.atomic_write(destination, b"# Conflicting bytes\n")

            rejected = self.publish(control, source, revision=0, expect=2)
            self.assertIn("different bytes", rejected.stderr)
            self.assertEqual(initial_raw, paths["ledger"].read_bytes())
            self.assertEqual(b"# Conflicting bytes\n", destination.read_bytes())


if __name__ == "__main__":
    unittest.main()
