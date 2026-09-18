import json
import os
import subprocess
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

from tools import ledger


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "legacy" / "idea-scout-r58"
FIXTURE = FIXTURE_DIR / "rev-058-ledger.json"
CLI = ["python3", str(ROOT / "tools" / "ledger.py")]


def run(*args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run([*CLI, *args], text=True, capture_output=True)
    if result.returncode != 0:
        raise AssertionError(f"expected 0, got {result.returncode}: {result.stdout}\n{result.stderr}")
    return result


def tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class LegacyDiagnosticsV110Tests(unittest.TestCase):
    def test_public_cli_reproduces_r58_structural_diagnosis_read_only(self) -> None:
        before = tree_bytes(FIXTURE_DIR)
        first = run("diagnose-legacy", "--file", str(FIXTURE))
        after_first = tree_bytes(FIXTURE_DIR)
        second = run("diagnose-legacy", "--file", str(FIXTURE))
        after_second = tree_bytes(FIXTURE_DIR)

        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(before, after_first)
        self.assertEqual(before, after_second)
        diagnostic = json.loads(first.stdout)
        self.assertTrue(diagnostic["read_only"])
        self.assertTrue(diagnostic["valid"])
        self.assertEqual("1.0", diagnostic["schema_version"])
        self.assertFalse(diagnostic["mutation_eligible"])
        self.assertIn("semantic contract/minimum writer metadata", diagnostic["mutation_reason"])
        self.assertEqual(58, diagnostic["revision"])
        self.assertEqual({"phase": "EXECUTE", "control": "BLOCKED"}, diagnostic["lifecycle"])

        intersections = diagnostic["accepted_design_intersections"]
        self.assertEqual(13, intersections["total_count"])
        self.assertEqual(9, intersections["distinct_ticket_count"])
        self.assertEqual(13, len(intersections["records"]))
        self.assertEqual(
            sorted(intersections["records"], key=lambda item: (item["contract_ref"], item["ticket_ref"])),
            intersections["records"],
        )

        self.assertEqual(1, len(diagnostic["current_candidates"]))
        candidate = diagnostic["current_candidates"][0]
        self.assertEqual("ef8da4ff49cc7f8014d90f463acf8319ad7c1335", candidate["candidate_sha"])
        self.assertEqual("continuation_only", candidate["qualification"])
        self.assertFalse(candidate["integrated"])
        self.assertEqual("BLOCKED", candidate["ticket_state"])

        current_reviews = diagnostic["current_review_attempts"]
        self.assertEqual(1, len(current_reviews))
        self.assertEqual("T02-R17-REVIEW-CODE-05", current_reviews[0]["attempt_ref"])
        self.assertEqual("RETURNED", current_reviews[0]["state"])
        self.assertEqual(3, current_reviews[0]["finding_count"])
        self.assertEqual(7, diagnostic["historical_ticket_review_findings"]["finding_count"])
        self.assertEqual(11, diagnostic["historical_design_findings"]["finding_count"])

        blockers = diagnostic["active_external_blockers"]
        self.assertEqual(["issue-62c0073109c9529a"], [item["issue_ref"] for item in blockers])
        next_action = diagnostic["next_action_analysis"]
        self.assertEqual("await_blocked_candidate_review", next_action["stored"]["kind"])
        self.assertTrue(next_action["stale"])
        self.assertEqual(
            [
                ("T02-R17-REVIEW-CODE-05", "review", "RETURNED"),
                ("T02-R17-WORKER-05", "worker", "RETURNED"),
            ],
            [(item["attempt_ref"], item["kind"], item["state"]) for item in next_action["referenced_attempts"]],
        )
        self.assertTrue(all("RETURNED" in item["reason"] for item in next_action["stale_reasons"]))

    def test_analysis_opens_only_the_selected_ledger_and_never_checks_referenced_paths(self) -> None:
        selected = FIXTURE.resolve()
        loaded_schema = ledger.schema()
        opened: list[str] = []
        touched: list[tuple[str, str]] = []

        def normalized(path: Path) -> str:
            return os.path.abspath(os.fspath(path))

        original_open = Path.open
        original_lstat = Path.lstat
        original_stat = Path.stat
        original_exists = Path.exists
        original_is_file = Path.is_file
        original_is_symlink = Path.is_symlink

        def guarded_open(path: Path, *args, **kwargs):
            actual = normalized(path)
            opened.append(actual)
            if actual != str(selected):
                raise AssertionError(f"diagnostic opened an unselected file: {actual}")
            return original_open(path, *args, **kwargs)

        def guard_path_method(method_name: str, original):
            def guarded(path: Path, *args, **kwargs):
                actual = normalized(path)
                touched.append((method_name, actual))
                if actual != str(selected):
                    raise AssertionError(f"diagnostic checked an unselected path: {actual}")
                return original(path, *args, **kwargs)
            return guarded

        with (
            mock.patch.object(ledger, "schema", return_value=loaded_schema),
            mock.patch.object(Path, "open", guarded_open),
            mock.patch.object(Path, "lstat", guard_path_method("lstat", original_lstat)),
            mock.patch.object(Path, "stat", guard_path_method("stat", original_stat)),
            mock.patch.object(Path, "exists", guard_path_method("exists", original_exists)),
            mock.patch.object(Path, "is_file", guard_path_method("is_file", original_is_file)),
            mock.patch.object(Path, "is_symlink", guard_path_method("is_symlink", original_is_symlink)),
        ):
            result = ledger.cmd_diagnose_legacy(Namespace(file=str(selected)))

        self.assertTrue(result["valid"])
        self.assertEqual([str(selected)], opened)
        self.assertEqual([("lstat", str(selected))], touched)

    def test_malformed_json_and_invalid_known_schema_return_read_only_diagnostics(self) -> None:
        original = json.loads(FIXTURE.read_text(encoding="utf-8"))
        invalid = json.loads(FIXTURE.read_text(encoding="utf-8"))
        invalid["lifecycle"]["control"] = "NOT_A_CONTROL"
        cases = ((b"{not json", "corrupt ledger JSON"), (ledger.canonical_bytes(invalid), "not in enum"))

        with tempfile.TemporaryDirectory() as directory:
            for index, (raw, message) in enumerate(cases):
                with self.subTest(index=index), tempfile.TemporaryDirectory(dir=directory) as nested:
                    path = Path(nested) / "legacy.json"
                    path.write_bytes(raw)
                    before = path.read_bytes()
                    result = run("diagnose-legacy", "--file", str(path))
                    diagnostic = json.loads(result.stdout)
                    self.assertTrue(diagnostic["read_only"])
                    self.assertFalse(diagnostic["valid"])
                    self.assertFalse(diagnostic["mutation_eligible"])
                    self.assertIn(message, diagnostic["validation_error"])
                    self.assertEqual(ledger.sha256_bytes(before), diagnostic["source_sha256"])
                    self.assertEqual(before, path.read_bytes())
                    self.assertNotIn("Traceback", result.stderr)
                    self.assertNotIn("Traceback", result.stdout)

        self.assertEqual("1.0", original["schema_version"])


if __name__ == "__main__":
    unittest.main()
