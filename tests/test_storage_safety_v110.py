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


def run(*args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run([*CLI, *args], text=True, capture_output=True)
    if result.returncode:
        raise AssertionError(f"command failed: {result.stdout}\n{result.stderr}")
    return result


class StorageSafetyV110Tests(unittest.TestCase):
    def make_run(self, root: Path) -> tuple[Path, dict[str, Path], Path]:
        control, repo = root / "control", root / "repo"
        control.mkdir()
        repo.mkdir()
        run("init", "--control-root", str(control), "--repo-root", str(repo), "--run-id", "storage-run", "--owner-token", "owner-a")
        intent = root / "intent-v1.md"
        intent.write_bytes(b"# Original intent\n")
        run(
            "publish-intent", "--control-root", str(control), "--run-id", "storage-run",
            "--owner-token", "owner-a", "--revision", "0", "--intent-file", str(intent),
            "--doc-id", "D-intent-v1", "--doc-version", "v1", "--intent-revision", "intent-v1",
        )
        return control, ledger.paths(control, "storage-run"), intent

    def amend_args(
        self,
        control: Path,
        source: Path,
        *,
        owner: str = "owner-a",
        revision: int = 1,
        doc_id: str = "D-intent-v2",
        doc_version: str = "v2",
        intent_revision: str = "intent-v2",
        amendment_id: str = "AM-1",
    ) -> Namespace:
        return Namespace(
            control_root=str(control), run_id="storage-run", owner_token=owner, revision=revision,
            intent_file=str(source), doc_id=doc_id, doc_version=doc_version,
            intent_revision=intent_revision, amendment_id=amendment_id, authority_ref="user-message",
        )

    def test_amend_rejections_leave_canonical_bytes_and_ledger_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            control, paths, _ = self.make_run(root)
            state, before_ledger = ledger.load_state(paths)
            original_doc = Path(state["documents"][0]["path"])
            before_document = original_doc.read_bytes()
            changed = root / "changed.md"
            changed.write_bytes(b"# Changed intent\n")

            with self.assertRaisesRegex(ledger.LedgerError, "owner token mismatch"):
                ledger.cmd_amend(self.amend_args(control, changed, owner="stale-owner", doc_id="D-intent-v1", doc_version="v1"))
            self.assertEqual(before_document, original_doc.read_bytes())
            self.assertEqual(before_ledger, paths["ledger"].read_bytes())

            with self.assertRaisesRegex(ledger.LedgerError, "revision mismatch"):
                ledger.cmd_amend(self.amend_args(control, changed, revision=0, doc_id="D-intent-v1", doc_version="v1"))
            self.assertEqual(before_document, original_doc.read_bytes())
            self.assertEqual(before_ledger, paths["ledger"].read_bytes())

            accepted = ledger.cmd_amend(self.amend_args(control, changed))
            self.assertEqual(2, accepted["revision"])
            state, committed = ledger.load_state(paths)
            duplicate_source = root / "duplicate.md"
            duplicate_source.write_bytes(b"# A different duplicate\n")
            with self.assertRaisesRegex(ledger.LedgerError, "amendment ID already exists"):
                ledger.cmd_amend(self.amend_args(control, duplicate_source, revision=2, doc_id="D-intent-v3", doc_version="v3"))
            self.assertFalse((paths["docs"] / "D-intent-v3").exists())
            self.assertEqual(committed, paths["ledger"].read_bytes())

    def test_amend_canonical_destination_conflict_and_identical_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            control, paths, _ = self.make_run(root)
            source = root / "intent-v2.md"
            source.write_bytes(b"# Intent v2\n")
            destination = paths["docs"] / "D-intent-v2" / "v2.md"
            destination.parent.mkdir(parents=True)
            destination.write_bytes(b"conflicting pre-existing bytes\n")
            before_ledger = paths["ledger"].read_bytes()
            with self.assertRaisesRegex(ledger.LedgerError, "different bytes"):
                ledger.cmd_amend(self.amend_args(control, source))
            self.assertEqual(b"conflicting pre-existing bytes\n", destination.read_bytes())
            self.assertEqual(before_ledger, paths["ledger"].read_bytes())

            destination.unlink()
            destination.write_bytes(source.read_bytes())
            result = ledger.cmd_amend(self.amend_args(control, source))
            self.assertEqual(2, result["revision"])
            self.assertEqual(source.read_bytes(), destination.read_bytes())

    def test_amend_snapshot_failure_is_observable_and_exact_retry_reconciles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            control, paths, _ = self.make_run(root)
            source = root / "intent-v2.md"
            source.write_bytes(b"# Intent v2\n")
            before, before_raw = ledger.load_state(paths)
            args = self.amend_args(control, source)
            with mock.patch.object(ledger, "write_snapshot", side_effect=OSError("injected snapshot failure")):
                with self.assertRaisesRegex(ledger.LedgerError, "revision 2 committed.*snapshot publication failed"):
                    ledger.cmd_amend(args)
            committed, committed_raw = ledger.load_state(paths)
            self.assertEqual(before["revision"] + 1, committed["revision"])
            self.assertEqual(ledger.sha256_bytes(before_raw), committed["previous_publication_hash"])
            self.assertNotEqual(before_raw, committed_raw)

            retry = ledger.cmd_amend(args)
            self.assertTrue(retry["idempotent"])
            self.assertEqual(committed["revision"], retry["revision"])
            self.assertEqual(committed_raw, paths["ledger"].read_bytes())
            snapshot = ledger.snapshot_path(paths, committed, "amendment")
            self.assertTrue(snapshot.exists())
            self.assertEqual(committed_raw, snapshot.read_bytes())

    def test_stored_payload_verifies_hash_namespace_and_regular_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            control, paths, _ = self.make_run(root)
            raw = ledger.canonical_bytes({"kind": "fixture", "value": 7})
            digest = ledger.object_store(paths, raw)
            self.assertEqual({"kind": "fixture", "value": 7}, ledger.stored_payload(paths, f"objects/{digest}", "test object"))

            (paths["objects"] / digest).write_bytes(ledger.canonical_bytes({"kind": "tampered"}))
            with self.assertRaisesRegex(ledger.LedgerError, "hash does not match"):
                ledger.stored_payload(paths, f"objects/{digest}", "tampered object")
            for bad_ref in ("objects/../ledger.json", "objects/ABC", "objects/" + "a" * 63):
                with self.subTest(ref=bad_ref), self.assertRaisesRegex(ledger.LedgerError, "immutable object reference"):
                    ledger.stored_payload(paths, bad_ref, "bad object")

            symlink_raw = ledger.canonical_bytes({"kind": "symlink"})
            symlink_digest = ledger.sha256_bytes(symlink_raw)
            outside = root / "outside.json"
            outside.write_bytes(symlink_raw)
            (paths["objects"] / symlink_digest).symlink_to(outside)
            with self.assertRaisesRegex(ledger.LedgerError, "immutable object is unavailable"):
                ledger.stored_payload(paths, f"objects/{symlink_digest}", "symlink object")

            escaped_objects = root / "escaped-objects"
            escaped_objects.mkdir()
            (escaped_objects / symlink_digest).write_bytes(symlink_raw)
            original_namespace = paths["run"] / "objects-original"
            paths["objects"].rename(original_namespace)
            paths["objects"].symlink_to(escaped_objects, target_is_directory=True)
            with self.assertRaisesRegex(ledger.LedgerError, "immutable object is unavailable"):
                ledger.stored_payload(paths, f"objects/{symlink_digest}", "escaped namespace object")

    def test_object_store_never_replaces_conflicting_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            control, paths, _ = self.make_run(root)
            raw = b'{"kind":"original"}\n'
            digest = ledger.sha256_bytes(raw)
            paths["objects"].mkdir(parents=True)
            target = paths["objects"] / digest
            target.write_bytes(b"different")
            with self.assertRaisesRegex(ledger.LedgerError, "immutable object collision"):
                ledger.object_store(paths, raw)
            self.assertEqual(b"different", target.read_bytes())

    def test_transition_write_plan_discards_rejected_objects_and_publishes_exact_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            control, paths, _ = self.make_run(root)
            before_raw = paths["ledger"].read_bytes()
            rejected_raw = ledger.canonical_bytes({"kind": "rejected"})

            def rejected_change(_state: dict) -> None:
                ledger.object_store(paths, rejected_raw)
                ledger.fail("semantic rejection after staging")

            with self.assertRaisesRegex(ledger.LedgerError, "semantic rejection"):
                ledger.transaction(paths, "owner-a", 1, rejected_change)
            self.assertEqual(before_raw, paths["ledger"].read_bytes())
            self.assertFalse(paths["objects"].exists())

            committed_raw = ledger.canonical_bytes({"kind": "committed", "value": 11})
            committed_digest: list[str] = []

            def accepted_change(state: dict) -> None:
                committed_digest.append(ledger.object_store(paths, committed_raw))
                state["lifecycle"]["reason"] = "storage-plan-test"

            committed = ledger.transaction(paths, "owner-a", 1, accepted_change)
            ref = f"objects/{committed_digest[0]}"
            self.assertEqual(2, committed["revision"])
            self.assertEqual(committed_digest[0], ledger.sha256_file(paths["objects"] / committed_digest[0]))
            self.assertEqual({"kind": "committed", "value": 11}, ledger.stored_payload(paths, ref, "committed object"))

    def test_ingest_preserves_the_exact_validated_return_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            control, paths, _ = self.make_run(root)
            attempt_root = paths["scratch"] / "A-return"
            attempt_root.mkdir(parents=True)
            inbox = attempt_root / "return.json"
            original = b'{ "identity": {"attempt_id":"A-return","run_id":"storage-run"}, "value": 1 }\n'
            inbox.write_bytes(original)

            original_read_text = Path.read_text

            def reject_inbox_reread(path: Path, *args: object, **kwargs: object) -> str:
                if path == inbox:
                    raise AssertionError("validated inbox must not be read a second time")
                return original_read_text(path, *args, **kwargs)

            with mock.patch.object(Path, "read_text", new=reject_inbox_reread):
                payload, digest, validated_raw = ledger.ingest_payload(
                    paths, {"run_id": "storage-run"}, "A-return", inbox,
                )
            self.assertEqual(original, validated_raw)
            self.assertEqual(ledger.sha256_bytes(original), digest)
            self.assertEqual({"identity": {"attempt_id": "A-return", "run_id": "storage-run"}, "value": 1}, payload)
            inbox.write_bytes(b'{"identity":{"attempt_id":"A-return","run_id":"storage-run"},"value":2}\n')

            published_digest = ledger.object_store(paths, validated_raw)
            self.assertEqual(digest, published_digest)
            stored_raw = (paths["objects"] / digest).read_bytes()
            self.assertEqual(original, stored_raw)
            self.assertEqual(digest, ledger.sha256_bytes(stored_raw))
            self.assertEqual(payload, json.loads(stored_raw))


if __name__ == "__main__":
    unittest.main()
