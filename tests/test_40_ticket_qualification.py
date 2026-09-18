import unittest

from experiments.v1_40_ticket_qualification import run_qualification


class FortyTicketQualificationTests(unittest.TestCase):
    def test_synthetic_forty_ticket_lifecycle(self) -> None:
        result = run_qualification()
        self.assertTrue(result["qualified"])
        self.assertEqual(40, result["ticket_count"])
        self.assertEqual(40, result["dashboard_ticket_count"])
        self.assertTrue(result["premature_readiness_rejected"])
        self.assertTrue(result["repair_path"])
        self.assertTrue(result["pause_seen"])
        self.assertTrue(result["recovery_seen"])
        self.assertTrue(result["schema_round_trip"])
        self.assertEqual("ACCEPTED", result["terminal_control"])
        self.assertEqual(82, result["attempt_registrations"])
        self.assertEqual(82, result["spawn_calls"])
        self.assertEqual(164, result["runtime_observation_refs"])
        # Keep Phase D's real-Git candidate proofs. Phase G adds 164 separate,
        # CAS-fenced, content-addressed runtime observations (start/stop for
        # 40 workers + 1 repair worker + 41 reviewers). Allow a principled
        # Phase G ceiling below 270 seconds without permitting omitted receipts.
        self.assertLess(result["elapsed_seconds"], 270)
        self.assertLess(result["ledger_bytes"], 8 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
