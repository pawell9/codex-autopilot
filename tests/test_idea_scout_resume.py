import json
import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("/Users/pawell_9/Documents/Pet-project - поиск идей проектов")


class IdeaScoutResumeTests(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("CODEX_AUTOPILOT_RUN_LEGACY_IDEA_SCOUT_AUDIT") == "1",
        "legacy production-checkpoint audit is opt-in; normal tests use sanitized fixtures",
    )
    def test_exact_v5_resume_on_disposable_copy(self):
        result = subprocess.run(["python3", str(ROOT / "experiments" / "idea_scout_v5_resume_dry_run.py")], cwd=ROOT, text=True, capture_output=True)
        if result.returncode:
            self.fail(f"dry run failed:\n{result.stdout}\n{result.stderr}")
        report = json.loads(result.stdout)
        self.assertTrue(report["qualified"])
        self.assertEqual(31, report["disposable_result"]["publication_revision"])
        self.assertEqual(33, report["disposable_result"]["final_revision"])
        self.assertEqual("c0d235e71d7bed87b9da2141767ad17ad66fe9cd1070ff115ecb989cee3c1f33", report["source_unchanged"]["v5_raw_sha256"])
        self.assertEqual("b67dfaebe64bbf80bf76d535bff2cf4b4eed12ee7030821f7bb6c59dddc8e0c9", report["source_unchanged"]["ledger_sha256"])


if __name__ == "__main__":
    unittest.main()
