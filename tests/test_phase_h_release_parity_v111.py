from __future__ import annotations

import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from experiments import v111_release_qualification as qualification


ROOT = Path(__file__).resolve().parents[1]


class PhaseHReleaseParityTests(unittest.TestCase):
    def test_reproducible_release_qualification_passes(self) -> None:
        result = subprocess.run(
            ["python3", str(ROOT / "experiments" / "v111_release_qualification.py")],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["qualified"])
        self.assertEqual("v1.1.1", report["release"])
        self.assertEqual(21, report["source"]["files"])
        self.assertEqual("UNSUPPORTED", report["native_runtime"]["status"])

    def test_source_hash_tampering_fails_closed(self) -> None:
        _, source, _, _ = qualification.load_artifacts(ROOT)
        tampered = copy.deepcopy(source)
        tampered["files"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(qualification.QualificationError, "source hash mismatch"):
            qualification.verify_source_manifest(ROOT, tampered)

    def test_fixture_inventory_cannot_hide_a_test_module(self) -> None:
        _, _, inventory, _ = qualification.load_artifacts(ROOT)
        tampered = copy.deepcopy(inventory)
        tampered["suite"]["test_modules"] = tampered["suite"]["test_modules"][:-1]
        with self.assertRaisesRegex(qualification.QualificationError, "test inventory mismatch"):
            qualification.verify_fixture_inventory(ROOT, tampered)

    def test_content_manifest_detects_fixture_tamper(self) -> None:
        _, _, inventory, _ = qualification.load_artifacts(ROOT)
        tampered = copy.deepcopy(inventory)
        tampered["_content"]["files"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(qualification.QualificationError, "content hash mismatch"):
            qualification.verify_fixture_inventory(ROOT, tampered)

    def test_content_manifest_detects_missing_and_extra_paths(self) -> None:
        _, _, inventory, _ = qualification.load_artifacts(ROOT)
        missing = copy.deepcopy(inventory)
        missing["_content"]["files"] = missing["_content"]["files"][1:]
        with self.assertRaisesRegex(qualification.QualificationError, "content inventory path mismatch"):
            qualification.verify_fixture_inventory(ROOT, missing)

        extra = copy.deepcopy(inventory)
        extra["_content"]["files"].append({
            "path": "README.md", "bytes": (ROOT / "README.md").stat().st_size,
            "sha256": __import__("hashlib").sha256((ROOT / "README.md").read_bytes()).hexdigest(),
        })
        with self.assertRaisesRegex(qualification.QualificationError, "content inventory path mismatch"):
            qualification.verify_fixture_inventory(ROOT, extra)

    def test_environment_enforces_git_minimum_major(self) -> None:
        _, _, _, environment = qualification.load_artifacts(ROOT)
        tampered = copy.deepcopy(environment)
        tampered["runtime"]["git"]["minimum_major"] = 999
        with self.assertRaisesRegex(qualification.QualificationError, "Git 999"):
            qualification.verify_environment(ROOT, tampered)

    def test_fake_runtime_is_deterministic_and_conflicting_replay_is_rejected(self) -> None:
        first = qualification.fake_runtime_conformance()
        second = qualification.fake_runtime_conformance()
        self.assertEqual(first, second)
        runtime = qualification.FakeRuntime("attempt-test")
        runtime.observe("event-1", "start")
        runtime.observe("event-1", "start")
        with self.assertRaisesRegex(qualification.QualificationError, "conflicting runtime replay"):
            runtime.observe("event-1", "stop")

    def test_native_runtime_boundary_is_explicit_and_fail_closed(self) -> None:
        _, _, _, environment = qualification.load_artifacts(ROOT)
        native = environment["_runtime"]["native_runtime"]
        self.assertEqual("UNSUPPORTED", native["status"])
        self.assertTrue(native["adapter_bound"])
        self.assertFalse(native["fake_receipts_are_native_proof"])
        with self.assertRaises(qualification.NativeRuntimeUnsupported):
            qualification.require_native_runtime()

    def test_install_parity_is_checked_in_an_isolated_destination(self) -> None:
        _, source, _, _ = qualification.load_artifacts(ROOT)
        entries = qualification.verify_source_manifest(ROOT, source)
        report = qualification.verify_install_parity(ROOT, entries)
        self.assertEqual(len(entries), report["files"])
        self.assertTrue(report["isolated"])
        self.assertEqual("1.1.1", report["runtime_version"])


if __name__ == "__main__":
    unittest.main()
