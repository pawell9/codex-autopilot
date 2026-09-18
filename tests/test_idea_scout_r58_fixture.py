import hashlib
import json
import re
import tempfile
import unittest
from pathlib import Path


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "legacy" / "idea-scout-r58"
ARCHIVE_SHA256 = "3ff2fd367680aa2066007fe66c2ded8f7835561698e4dc4a9576f6e283dc5772"
WORKER05_CANDIDATE = "ef8da4ff49cc7f8014d90f463acf8319ad7c1335"
EXTERNAL_BLOCKER = "issue-62c0073109c9529a"
SOURCE_ARTIFACTS = {
    "rev-058-ledger.json": {
        "source_path": "autopilot-hardening-evidence/state/successor/rev-058-ledger.json",
        "sha256": "dbfe634b0ea9bb94cc91f14f249d38b5947b74f0c285c9a80d131f74d582a894",
    },
    "review05-packet.json": {
        "source_path": "autopilot-hardening-evidence/reviews/review05-packet.json",
        "sha256": "e8b28341a5e2202e22c0281de105780bc92b9d5079f7104df9475bdf26001a00",
    },
    "review05-return.json": {
        "source_path": "autopilot-hardening-evidence/reviews/review05-return.json",
        "sha256": "e977b0f75bde0456a1a644fb82ad683f31ae10926b804b5798b8912ddc5dcd1c",
    },
    "worker05-continuation-receipt.json": {
        "source_path": "autopilot-hardening-evidence/receipts/worker05-continuation-receipt.json",
        "sha256": "8391797669bfcfe374950008c9dc3a343724ad4cf687b405ed870586c7d3c0d0",
    },
}


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def load_json(name):
    return json.loads((FIXTURE / name).read_text(encoding="utf-8"))


class IdeaScoutR58FixtureTests(unittest.TestCase):
    def test_manifest_and_archive_checksums_match_byte_faithful_fixture(self):
        manifest = load_json("manifest.json")
        self.assertEqual(ARCHIVE_SHA256, manifest["source_archive"]["sha256"])
        self.assertIn("literal placeholder <REDACTED_OWNER_TOKEN>", manifest["redaction_and_sanitization"])
        self.assertIn("byte-identical", manifest["redaction_and_sanitization"])

        entries = manifest["files"]
        listed_paths = {entry["path"] for entry in entries}
        self.assertEqual(set(SOURCE_ARTIFACTS), listed_paths)
        self.assertEqual(listed_paths | {"manifest.json"}, {path.name for path in FIXTURE.iterdir() if path.is_file()})

        for entry in entries:
            expected = SOURCE_ARTIFACTS[entry["path"]]
            self.assertEqual(expected["source_path"], entry["source_path"])
            self.assertEqual(expected["sha256"], entry["sha256"])
            fixture_path = FIXTURE / entry["path"]
            actual_hash = sha256(fixture_path.read_bytes())
            self.assertEqual(entry["sha256"], actual_hash, entry["path"])

    def test_revision_58_diagnosis_reproduces_review_and_producer_counts(self):
        ledger = load_json("rev-058-ledger.json")
        packet = load_json("review05-packet.json")
        review_return = load_json("review05-return.json")
        self.assertEqual(58, ledger["revision"])
        self.assertEqual("<REDACTED_OWNER_TOKEN>", ledger["owner"]["token"])

        publication = ledger["design_publication"]
        self.assertEqual("PUBLISHED", publication["status"])
        ticket_by_id = {ticket["id"]: ticket for ticket in ledger["tickets"]}
        published_contracts = {
            contract["id"]: contract
            for contract in ledger["contracts"]
            if contract["id"] in publication["contract_refs"]
        }
        intersections = []
        for ticket_id in publication["ticket_refs"]:
            ticket_inputs = set(ticket_by_id[ticket_id]["contract_refs"])
            produced_by_ticket = {
                contract_id
                for contract_id, contract in published_contracts.items()
                if ticket_id in contract["producer_refs"]
            }
            intersections.extend((ticket_id, contract_id) for contract_id in ticket_inputs & produced_by_ticket)
        self.assertEqual(13, len(intersections))
        self.assertEqual(9, len({ticket_id for ticket_id, _ in intersections}))

        current_review_source = packet["identity"]["attempt_id"]
        current_findings = [finding for finding in ledger["findings"] if finding["source_ref"] == current_review_source]
        self.assertEqual("T02-R17-REVIEW-CODE-05", current_review_source)
        self.assertEqual(3, len(current_findings))
        self.assertEqual(3, len(review_return["findings"]))
        packet_hash = sha256((FIXTURE / "review05-packet.json").read_bytes())
        return_hash = sha256((FIXTURE / "review05-return.json").read_bytes())
        self.assertEqual(packet_hash, review_return["identity"]["packet_hash"])
        self.assertEqual(current_review_source, review_return["identity"]["attempt_id"])
        review_attempt = next(attempt for attempt in ledger["attempts"] if attempt["id"] == current_review_source)
        self.assertEqual(f"objects/{packet_hash}", review_attempt["packet_ref"])
        self.assertEqual(f"objects/{return_hash}", review_attempt["return_ref"])
        self.assertEqual([finding["id"] for finding in current_findings], review_attempt["finding_refs"])
        self.assertTrue(all("T02-R17" not in finding["affected_refs"] for finding in current_findings))

        historical_t02 = [
            finding
            for finding in ledger["findings"]
            if re.fullmatch(r"T02-R17-REVIEW-CODE-0[1-3]", finding["source_ref"])
        ]
        historical_design = [
            finding for finding in ledger["findings"] if finding["source_ref"].startswith(("G2-", "G3-"))
        ]
        self.assertEqual(7, len(historical_t02))
        self.assertEqual(11, len(historical_design))
        self.assertTrue(all(finding["invalidated_by"] == [] for finding in historical_t02))

        self.assertEqual("BLOCKED", ledger["lifecycle"]["control"])
        self.assertEqual("await_blocked_candidate_review", ledger["lifecycle"]["next_action"]["kind"])
        blocker = next(issue for issue in ledger["issues"] if issue["id"] == EXTERNAL_BLOCKER)
        self.assertEqual("blocking", blocker["impact"])
        self.assertEqual([], blocker["invalidated_by"])
        self.assertIn(EXTERNAL_BLOCKER, ledger["lifecycle"]["issue_refs"])

        continuation = load_json("worker05-continuation-receipt.json")
        continuation_hash = sha256((FIXTURE / "worker05-continuation-receipt.json").read_bytes())
        worker_attempt = next(attempt for attempt in ledger["attempts"] if attempt["id"] == "T02-R17-WORKER-05")
        self.assertEqual(WORKER05_CANDIDATE, continuation["candidate_sha"])
        self.assertEqual(WORKER05_CANDIDATE, worker_attempt["candidate_sha"])
        self.assertEqual(f"objects/{continuation_hash}", worker_attempt["continuation_ref"])
        self.assertEqual(EXTERNAL_BLOCKER, continuation["blocker_ref"])
        self.assertEqual("external", continuation["blocker_scope"])
        self.assertEqual("BLOCKED", continuation["return_status"])

    def test_append_only_rehearsal_log_leaves_fixture_source_bytes_unchanged(self):
        manifest = load_json("manifest.json")
        fixture_paths = [FIXTURE / entry["path"] for entry in manifest["files"]]
        before = {path.name: sha256(path.read_bytes()) for path in fixture_paths}
        source_hash = before["rev-058-ledger.json"]

        # This fixture-level probe records migration/recovery events beside a source hash;
        # it does not implement or claim to execute the production migration.
        with tempfile.TemporaryDirectory() as temporary_directory:
            event_log = Path(temporary_directory) / "migration-recovery.jsonl"
            for event_kind in ("migration-proposed", "recovery-rehearsal"):
                event = {
                    "event": event_kind,
                    "source_revision": 58,
                    "source_ledger_sha256": source_hash,
                }
                with event_log.open("ab") as stream:
                    stream.write(json.dumps(event, sort_keys=True).encode("utf-8") + b"\n")

            events = [json.loads(line) for line in event_log.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(["migration-proposed", "recovery-rehearsal"], [event["event"] for event in events])
            self.assertTrue(all(event["source_ledger_sha256"] == source_hash for event in events))

        after = {path.name: sha256(path.read_bytes()) for path in fixture_paths}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
