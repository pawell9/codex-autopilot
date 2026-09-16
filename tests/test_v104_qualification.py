import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class V104QualificationTests(unittest.TestCase):
    def test_realistic_offline_lifecycle_reaches_accepted(self) -> None:
        result = subprocess.run(["python3", str(ROOT / "experiments" / "v104_lifecycle_qualification.py")], cwd=ROOT, text=True, capture_output=True)
        if result.returncode:
            self.fail(f"qualification failed:\n{result.stdout}\n{result.stderr}")
        report = json.loads(result.stdout)
        self.assertTrue(report["qualified"])
        self.assertEqual("ACCEPTED", report["terminal"]["control"])
        self.assertEqual(3, len(report["design_history"]))
        self.assertEqual(["SUPERSEDED", "SUPERSEDED", "PUBLISHED"], [item["status"] for item in report["design_history"]])
        self.assertTrue(report["acceptance_rounds"][-1]["verdict"] == "PASS")


if __name__ == "__main__":
    unittest.main()
