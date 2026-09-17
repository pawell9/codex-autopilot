import copy
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


def write_json(path: Path, value: object) -> None:
    ledger.atomic_write(path, ledger.canonical_bytes(value))


class RequirementsAdoptionTests(unittest.TestCase):
    def fixture(self, root: Path, *, legacy_version: str = "1.0.0") -> tuple[Path, Path, Path]:
        control, repo = root / "control", root / "repo"
        control.mkdir(); repo.mkdir()
        run("init", "--control-root", str(control), "--repo-root", str(repo), "--run-id", "adopt-run", "--owner-token", "owner-a")
        paths = ledger.paths(control, "adopt-run")
        state, _ = ledger.load_state(paths)
        state["skill_version"] = legacy_version
        state.pop("runtime_provenance", None)
        ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
        intent = root / "intent.md"; intent.write_text("# Intent\n\nExplicit R-1 / C-1.\n", encoding="utf-8")
        run("publish-intent", "--control-root", str(control), "--run-id", "adopt-run", "--owner-token", "owner-a", "--revision", "0", "--intent-file", str(intent), "--doc-id", "D-intent", "--doc-version", "v1", "--intent-revision", "v1")
        run("gate", "--control-root", str(control), "--run-id", "adopt-run", "--owner-token", "owner-a", "--revision", "1", "--phase", "DESIGN", "--control", "BLOCKED", "--reason", "criteria_publication_gap", "--next-action", "adopt-requirements")
        state, _ = ledger.load_state(paths)
        manifest = {
            "publication_id": "RP-1", "version": "v1", "epoch": 0,
            "intent_revision": "v1", "intent_document_ref": "D-intent", "intent_document_hash": state["intent"]["document_hash"],
            "requirements": [{"id": "R-1", "version": "v1", "status": "active", "provenance_refs": ["D-intent"], "criterion_refs": ["C-1"]}],
            "criteria": [{"id": "C-1", "version": "v1", "requirement_refs": ["R-1"], "oracle": "explicit oracle", "status": "active", "source_ref": "D-intent"}],
        }
        manifest_path = root / "requirements.json"; write_json(manifest_path, manifest)
        return control, paths["run"], manifest_path

    def bundle(self, root: Path, control: Path) -> Path:
        state, _ = ledger.load_state(ledger.paths(control, "adopt-run"))
        docs = []
        for doc_id, kind in (("D-design", "design"), ("D-interfaces", "interfaces"), ("D-manifest", "manifest"), ("D-plan", "plan"), ("D-tickets", "tickets"), ("D-routes", "routes")):
            source = root / f"{doc_id}.md"; source.write_text(f"# {doc_id}\n", encoding="utf-8")
            docs.append({"id": doc_id, "version": "v1", "kind": kind, "source": str(source), "hash": ledger.sha256_file(source)})
        value = {
            "bundle_id": "B-1", "version": "v1", "epoch": 0, "intent_revision": "v1", "intent_document_ref": "D-intent", "intent_document_hash": state["intent"]["document_hash"],
            "documents": docs,
            "contracts": [{"id": "K-1", "version": "v1", "status": "active", "provenance_refs": ["D-interfaces"]}],
            "tickets": [{"id": "T-1", "goal_ref": "G-1", "criterion_refs": ["C-1"], "contract_refs": ["K-1"], "dependency_refs": [], "state": "PLANNED", "complexity": "bounded", "risk": "routine", "zone": [{"path": "app.txt", "operations": ["modify"]}]}],
            "routes": [{"id": "ROUTE-1", "capability": "worker", "reasoning": "fixture", "adequacy": "CONFIRMED", "context_grade": "PACKET_SCOPED"}],
        }
        target = root / "bundle.json"; write_json(target, value); return target

    def test_legacy_adoption_is_atomic_idempotent_and_binds_design(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); control, _, manifest = self.fixture(root)
            result = json.loads(run("adopt-requirements", "--control-root", str(control), "--run-id", "adopt-run", "--owner-token", "owner-a", "--revision", "2", "--manifest", str(manifest)).stdout)
            self.assertEqual(3, result["revision"]); self.assertFalse(result["idempotent"])
            retry = json.loads(run("adopt-requirements", "--control-root", str(control), "--run-id", "adopt-run", "--owner-token", "owner-a", "--revision", "2", "--manifest", str(manifest)).stdout)
            self.assertTrue(retry["idempotent"]); self.assertEqual(3, retry["revision"])
            paths = ledger.paths(control, "adopt-run")
            state, _ = ledger.load_state(paths)
            self.assertEqual("1.0.0", state["skill_version"])
            self.assertEqual("1.0.7", state["runtime_provenance"]["last_mutating_skill_version"])
            self.assertEqual("adopt-requirements-RP-1", state["runtime_provenance"]["applied_migrations"][0]["id"])
            bundle = self.bundle(root, control)
            run("publish-design-bundle", "--control-root", str(control), "--run-id", "adopt-run", "--owner-token", "owner-a", "--revision", "3", "--bundle", str(bundle))
            state, _ = ledger.load_state(paths)
            self.assertEqual(["C-1"], state["design_publication"]["criterion_refs"])
            self.assertEqual("RP-1", state["design_publication"]["requirements_publication_ref"])

    def test_conflicting_retry_and_unknown_refs_leave_ledger_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); control, _, manifest = self.fixture(root)
            run("adopt-requirements", "--control-root", str(control), "--run-id", "adopt-run", "--owner-token", "owner-a", "--revision", "2", "--manifest", str(manifest))
            paths = ledger.paths(control, "adopt-run"); original = paths["ledger"].read_bytes()
            changed = json.loads(manifest.read_text(encoding="utf-8")); changed["criteria"][0]["oracle"] = "conflict"; write_json(manifest, changed)
            rejected = run("adopt-requirements", "--control-root", str(control), "--run-id", "adopt-run", "--owner-token", "owner-a", "--revision", "2", "--manifest", str(manifest), expect=2)
            self.assertIn("different bytes", rejected.stderr); self.assertEqual(original, paths["ledger"].read_bytes())
            bundle = self.bundle(root, control); value = json.loads(bundle.read_text(encoding="utf-8")); value["tickets"][0]["criterion_refs"] = ["C-unknown"]; write_json(bundle, value)
            rejected = run("publish-design-bundle", "--control-root", str(control), "--run-id", "adopt-run", "--owner-token", "owner-a", "--revision", "3", "--bundle", str(bundle), expect=2)
            self.assertIn("unknown criterion", rejected.stderr); self.assertEqual(original, paths["ledger"].read_bytes())

    def test_unknown_contract_ticket_cycle_and_unordered_zone_overlap_reject(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); control, _, manifest = self.fixture(root)
            run("adopt-requirements", "--control-root", str(control), "--run-id", "adopt-run", "--owner-token", "owner-a", "--revision", "2", "--manifest", str(manifest))
            paths = ledger.paths(control, "adopt-run"); original = paths["ledger"].read_bytes()

            bundle = self.bundle(root, control)
            value = json.loads(bundle.read_text(encoding="utf-8")); value["tickets"][0]["contract_refs"] = ["K-unknown"]; write_json(bundle, value)
            rejected = run("publish-design-bundle", "--control-root", str(control), "--run-id", "adopt-run", "--owner-token", "owner-a", "--revision", "3", "--bundle", str(bundle), expect=2)
            self.assertIn("unknown contract", rejected.stderr); self.assertEqual(original, paths["ledger"].read_bytes())

            value = json.loads(self.bundle(root, control).read_text(encoding="utf-8")); value["tickets"][0]["dependency_refs"] = ["T-missing"]; write_json(bundle, value)
            self.assertIn("outside the bundle", run("validate", "--file", str(bundle), "--kind", "design_bundle", expect=2).stderr)

            value = json.loads(self.bundle(root, control).read_text(encoding="utf-8")); value["tickets"][0]["dependency_refs"] = ["T-1"]; write_json(bundle, value)
            self.assertIn("cycle", run("validate", "--file", str(bundle), "--kind", "design_bundle", expect=2).stderr)

            value = json.loads(self.bundle(root, control).read_text(encoding="utf-8")); second = copy.deepcopy(value["tickets"][0]); second["id"] = "T-2"; value["tickets"].append(second); write_json(bundle, value)
            self.assertIn("overlap", run("validate", "--file", str(bundle), "--kind", "design_bundle", expect=2).stderr)
            self.assertEqual(original, paths["ledger"].read_bytes())

    def test_unknown_schema_is_diagnostic_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); control, _, _ = self.fixture(root)
            paths = ledger.paths(control, "adopt-run"); state = json.loads(paths["ledger"].read_text(encoding="utf-8")); state["schema_version"] = "99.0"; write_json(paths["ledger"], state); original = paths["ledger"].read_bytes()
            result = json.loads(run("diagnose", "--control-root", str(control), "--run-id", "adopt-run").stdout)
            self.assertFalse(result["supported"]); self.assertTrue(result["read_only"]); self.assertEqual(original, paths["ledger"].read_bytes())

    def test_intent_amendment_invalidates_requirements_publication_and_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); control, _, manifest = self.fixture(root)
            run("adopt-requirements", "--control-root", str(control), "--run-id", "adopt-run", "--owner-token", "owner-a", "--revision", "2", "--manifest", str(manifest))
            amended = root / "intent-v2.md"; amended.write_text("# Intent v2\n\nChanged authority.\n", encoding="utf-8")
            run("amend", "--control-root", str(control), "--run-id", "adopt-run", "--owner-token", "owner-a", "--revision", "3", "--intent-file", str(amended), "--doc-id", "D-intent-v2", "--doc-version", "v2", "--intent-revision", "v2", "--amendment-id", "AM-requirements", "--authority-ref", "user")
            state, _ = ledger.load_state(ledger.paths(control, "adopt-run"))
            self.assertEqual("INVALIDATED", state["requirements_publications"][0]["status"])
            self.assertIn("AM-requirements", state["requirements_publications"][0]["invalidated_by"])
            self.assertTrue(all("AM-requirements" in item["invalidated_by"] for item in [*state["requirements"], *state["criteria"]]))
            before = ledger.paths(control, "adopt-run")["ledger"].read_bytes()
            rejected = run("adopt-requirements", "--control-root", str(control), "--run-id", "adopt-run", "--owner-token", "owner-a", "--revision", "3", "--manifest", str(manifest), expect=2)
            self.assertIn("historical/stale", rejected.stderr)
            self.assertEqual(before, ledger.paths(control, "adopt-run")["ledger"].read_bytes())

    def test_all_supported_legacy_creation_versions_validate_and_adopt(self) -> None:
        for version in ("1.0.0", "1.0.1", "1.0.2", "1.0.3", "1.0.4", "1.0.5"):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                control, _, manifest = self.fixture(root, legacy_version=version)
                paths = ledger.paths(control, "adopt-run")
                before, _ = ledger.load_state(paths)
                ledger.validate_ledger(before)
                result = json.loads(run(
                    "adopt-requirements", "--control-root", str(control),
                    "--run-id", "adopt-run", "--owner-token", "owner-a",
                    "--revision", "2", "--manifest", str(manifest),
                ).stdout)
                self.assertEqual(3, result["revision"])
                migrated, _ = ledger.load_state(paths)
                self.assertEqual(version, migrated["skill_version"])
                self.assertEqual(version, migrated["runtime_provenance"]["creation_skill_version"])
                self.assertEqual("1.0.7", migrated["runtime_provenance"]["last_mutating_skill_version"])
                ledger.validate_ledger(migrated)

    def test_reviewer_loss_closes_attempt_and_lease_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, _, manifest = self.fixture(root)
            run("adopt-requirements", "--control-root", str(control), "--run-id", "adopt-run", "--owner-token", "owner-a", "--revision", "2", "--manifest", str(manifest))
            bundle = self.bundle(root, control)
            published = json.loads(run("publish-design-bundle", "--control-root", str(control), "--run-id", "adopt-run", "--owner-token", "owner-a", "--revision", "3", "--bundle", str(bundle)).stdout)
            packet = {
                "identity": {"run_id": "adopt-run", "attempt_id": "A-review-lost", "epoch": 0, "source_revision": 4, "registration_revision": 4, "subject_revision": 4, "intent_revision": "v1"},
                "kind": "review", "mandate": "coverage", "subject_fingerprint": published["publication_hash"],
                "criteria": [{"criterion_id": "C-1"}], "axes": ["coverage"], "return_target": {"path": "return.json"},
            }
            packet_path = root / "review.json"; write_json(packet_path, packet)
            run("prepare-design-review", "--control-root", str(control), "--run-id", "adopt-run", "--owner-token", "owner-a", "--revision", "4", "--review-attempt-id", "A-review-lost", "--lease-id", "L-review-lost", "--packet", str(packet_path), "--review-kind", "coverage", "--reviewer-identity", "fixture-reviewer", "--reviewer-role", "coverage-reviewer")
            evidence = root / "stop.json"; write_json(evidence, {"status": "PASS", "writer_stopped": True, "observation": "synthetic reviewer crash"})
            result = json.loads(run("terminate-attempt", "--control-root", str(control), "--run-id", "adopt-run", "--owner-token", "owner-a", "--revision", "5", "--attempt-id", "A-review-lost", "--state", "LOST", "--lease-state", "released", "--evidence", str(evidence)).stdout)
            self.assertEqual(6, result["revision"])
            state, _ = ledger.load_state(ledger.paths(control, "adopt-run"))
            attempt = ledger.attempt_by_id(state, "A-review-lost")
            self.assertEqual("LOST", attempt["state"])
            self.assertEqual("released", attempt["lease"]["state"])
            self.assertEqual("BLOCKED", state["lifecycle"]["control"])

    def test_owner_takeover_increments_epoch_and_quarantines_inflight_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, _, manifest = self.fixture(root)
            run("adopt-requirements", "--control-root", str(control), "--run-id", "adopt-run", "--owner-token", "owner-a", "--revision", "2", "--manifest", str(manifest))
            published = json.loads(run("publish-design-bundle", "--control-root", str(control), "--run-id", "adopt-run", "--owner-token", "owner-a", "--revision", "3", "--bundle", str(self.bundle(root, control))).stdout)
            packet = {"identity": {"run_id": "adopt-run", "attempt_id": "A-review-takeover", "epoch": 0, "source_revision": 4, "registration_revision": 4, "subject_revision": 4, "intent_revision": "v1"}, "kind": "review", "mandate": "coverage", "subject_fingerprint": published["publication_hash"], "criteria": [{"criterion_id": "C-1"}], "axes": ["coverage"], "return_target": {"path": "return.json"}}
            packet_path = root / "takeover-review.json"; write_json(packet_path, packet)
            run("prepare-design-review", "--control-root", str(control), "--run-id", "adopt-run", "--owner-token", "owner-a", "--revision", "4", "--review-attempt-id", "A-review-takeover", "--lease-id", "L-review-takeover", "--packet", str(packet_path), "--review-kind", "coverage", "--reviewer-identity", "fixture-reviewer", "--reviewer-role", "coverage-reviewer")
            recovered = json.loads(run("recover", "--control-root", str(control), "--run-id", "adopt-run", "--owner-token", "owner-a", "--revision", "5", "--reason", "owner_transfer", "--takeover", "--new-owner-token", "owner-b", "--attestation-ref", "EV-old-owner-stopped").stdout)
            self.assertEqual(1, recovered["epoch"])
            state, _ = ledger.load_state(ledger.paths(control, "adopt-run"))
            self.assertEqual("owner-b", state["owner"]["token"])
            self.assertEqual("quarantined", ledger.attempt_by_id(state, "A-review-takeover")["lease"]["state"])
            stale = run("gate", "--control-root", str(control), "--run-id", "adopt-run", "--owner-token", "owner-a", "--revision", "6", "--control", "ACTIVE", expect=2)
            self.assertIn("owner token mismatch", stale.stderr)


if __name__ == "__main__":
    unittest.main()
