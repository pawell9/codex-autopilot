import copy
import json
import unittest
from pathlib import Path

from tools import dashboard, ledger


ROOT = Path(__file__).resolve().parents[1]


class DashboardCurrentnessTests(unittest.TestCase):
    def test_projection_does_not_resurrect_invalidated_blockers_or_acceptance(self):
        state = {
            "run_id": "dashboard-currentness",
            "revision": 9,
            "updated_at": "2026-09-16T00:00:00Z",
            "skill_version": "1.0.0",
            "schema_version": "1.0",
            "owner": {"epoch": 1},
            "intent": {"revision": "2"},
            "lifecycle": {"phase": "VERIFY", "control": "ACTIVE", "reason": None, "next_action": {"kind": "g5", "subject_refs": [], "preconditions": [], "read_refs": []}},
            "issues": [{"id": "ISS-old", "impact": "blocking", "invalidated_by": ["B-new"]}],
            "findings": [{"id": "F-old", "impact": "blocking", "invalidated_by": ["B-new"]}],
            "acceptance": [{"round": 1, "intent_revision": "1", "candidate_fingerprint": "old", "verdict": "PASS", "transport": "automatic", "invalidated_by": ["intent:2"]}],
            "attempts": [{"id": "A-old", "candidate_sha": "a" * 40, "candidate_tree_sha": "b" * 40, "invalidated_by": ["B-new"], "lease": {"state": "released"}}],
            "tickets": [], "operations": [], "decisions": [],
        }
        raw = ledger.canonical_bytes(state)
        projection = dashboard.project_ledger(copy.deepcopy(state), Path("/tmp/read-only-ledger.json"), raw)
        self.assertEqual([], projection["blockers"])
        self.assertIsNone(projection["candidate"]["current"])
        self.assertFalse(projection["findings"][0]["current"])
        self.assertNotEqual("passed", projection["gates"][5]["status"])


if __name__ == "__main__":
    unittest.main()
