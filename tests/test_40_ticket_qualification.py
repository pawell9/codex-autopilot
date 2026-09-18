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
        # Phase D gives every ordinary candidate a real Git commit, full
        # base-to-tree audit, and immutable proof-object verification.  Keep a
        # bounded wall-clock guard for the stronger 40-candidate workload.
        self.assertLess(result["elapsed_seconds"], 180)
        self.assertLess(result["ledger_bytes"], 8 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
