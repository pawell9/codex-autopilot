import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools import ledger
from tests.test_phase_g_runtime_observations_v110 import record_runtime_event


ROOT = Path(__file__).resolve().parents[1]
CLI = ["python3", str(ROOT / "tools" / "ledger.py")]


def run(*args: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run([*CLI, *args], text=True, capture_output=True)
    if result.returncode != expect:
        raise AssertionError(f"expected {expect}, got {result.returncode}: {result.stdout}\n{result.stderr}")
    return result


def write_json(path: Path, value: object) -> None:
    ledger.atomic_write(path, ledger.canonical_bytes(value))


class DesignPublicationTests(unittest.TestCase):
    def setup_g1(self, root: Path, *, run_id: str = "design-run") -> tuple[Path, Path, Path]:
        control, repo = root / "control", root / "repo"
        control.mkdir(); repo.mkdir()
        run("init", "--control-root", str(control), "--repo-root", str(repo), "--run-id", run_id, "--owner-token", "owner-a")
        intent = root / "intent.md"
        intent.write_text("# Product intent\n\nBuild the candidate.\n", encoding="utf-8")
        run("publish-intent", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-a", "--revision", "0", "--intent-file", str(intent), "--doc-id", "D-intent", "--doc-version", "v1", "--intent-revision", "intent-v2")
        run("gate", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-a", "--revision", "1", "--phase", "DESIGN", "--control", "BLOCKED", "--reason", "missing_design_publication", "--next-action", "publish-design-bundle")
        return control, repo, ledger.paths(control, run_id)["run"]

    def bundle(self, root: Path, control: Path, run_id: str = "design-run", *, bundle_id: str = "B-design-v1") -> Path:
        paths = ledger.paths(control, run_id)
        state, _ = ledger.load_state(paths)
        docs = []
        for doc_id, kind in (("D-design", "design"), ("D-interfaces", "interfaces"), ("D-manifest", "manifest"), ("D-plan", "plan"), ("D-tickets", "tickets"), ("D-routes", "routes")):
            source = root / f"{doc_id}.md"
            source.write_text(f"# {doc_id}\n\nkind: {kind}\n", encoding="utf-8")
            docs.append({"id": doc_id, "version": "v1", "kind": kind, "source": str(source), "hash": ledger.sha256_file(source), "section_anchors": []})
        value = {
            "bundle_id": bundle_id, "version": "v1", "epoch": state["owner"]["epoch"], "intent_revision": state["intent"]["current_revision"],
            "intent_document_ref": state["intent"]["document_ref"], "intent_document_hash": state["intent"]["document_hash"],
            "documents": docs,
            "contracts": [{"id": "K-design", "version": "v1", "status": "active", "provenance_refs": ["D-interfaces"], "producer_refs": [], "consumer_refs": ["C-1"], "implementation_availability": "available", "implementation_availability_evidence_refs": ["fixture:design-contract-available"]}],
            "tickets": [{"id": "T-design", "goal_ref": "G-design", "criterion_refs": ["C-1"], "contract_refs": ["K-design"], "dependency_refs": [], "state": "PLANNED", "verification_ref": "design-oracle", "complexity": "bounded", "risk": "routine", "zone": [{"path": "app.txt", "operations": ["create"]}], "current_attempt": None, "replacement_refs": []}],
            "routes": [{"id": "R-design", "capability": "reviewer", "reasoning": "qualified fixture", "requested_binding": "fixture-reviewer", "observed_binding": "fixture-reviewer", "adequacy": "CONFIRMED", "context_grade": "PACKET_SCOPED"}],
        }
        # The fixture's G1 criterion is part of the canonical design binding.
        state["criteria"] = [{"id": "C-1", "version": "v1", "requirement_refs": [], "oracle": "design oracle", "status": "active"}]
        ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
        return_path = root / f"{bundle_id}.json"
        write_json(return_path, value)
        return return_path

    def publish(self, control: Path, bundle: Path, *, revision: int = 2, expect: int = 0) -> subprocess.CompletedProcess[str]:
        return run("publish-design-bundle", "--control-root", str(control), "--run-id", "design-run", "--owner-token", "owner-a", "--revision", str(revision), "--bundle", str(bundle), expect=expect)

    def review_packet(self, root: Path, control: Path, attempt_id: str, review_kind: str, *, source_revision: int) -> Path:
        state, _ = ledger.load_state(ledger.paths(control, "design-run"))
        packet = {"identity": {"run_id": "design-run", "attempt_id": attempt_id, "epoch": 0, "source_revision": state["revision"], "intent_revision": "intent-v2"}, "kind": "review", "mandate": f"design {review_kind}", "subject_fingerprint": state["design_publication"]["publication_hash"], "criteria": [{"criterion_id": "C-1"}], "axes": [review_kind], "return_target": {"path": "return.json"}}
        packet_path = root / f"{attempt_id}.json"
        write_json(packet_path, packet)
        return packet_path

    def prepare_review(self, control: Path, packet: Path, attempt_id: str, kind: str, revision: int) -> None:
        current, _ = ledger.load_state(ledger.paths(control, "design-run"))
        run("prepare-design-review", "--control-root", str(control), "--run-id", "design-run", "--owner-token", "owner-a", "--revision", str(current["revision"]), "--review-attempt-id", attempt_id, "--lease-id", f"L-{attempt_id}", "--packet", str(packet), "--review-kind", kind, "--reviewer-identity", "reviewer@example.invalid", "--reviewer-role", "independent-design-reviewer")

    def finish_review(self, root: Path, control: Path, attempt_id: str, revision: int, *, verdict: str = "PASS") -> None:
        paths = ledger.paths(control, "design-run")
        state, _ = ledger.load_state(paths)
        attempt = next(item for item in state["attempts"] if item["id"] == attempt_id)
        returned = {"identity": {"run_id": "design-run", "attempt_id": attempt_id, "packet_hash": attempt["packet_hash"], "epoch": 0, "source_revision": attempt["packet_source_revision"], "registration_revision": attempt["packet_registration_revision"], "subject_revision": attempt["subject_revision"], "intent_revision": "intent-v2"}, "subject_fingerprint": state["design_publication"]["publication_hash"], "verdict": verdict, "coverage": [{"criterion_id": "C-1", "outcome": "fulfilled" if verdict == "PASS" else "unverifiable", "evidence_refs": ["EV-review"]}], "checks": [{"check_id": "design-check", "axis": attempt["mode"], "outcome": "fulfilled" if verdict == "PASS" else "not_run", "actual": "fixture", "evidence_ref": "EV-review"}], "context_refs": ["clean-design-review"], "findings": []}
        inbox = paths["scratch"] / attempt_id / "return.json"
        write_json(inbox, returned)
        record_runtime_event(control, "design-run", "owner-a", paths, attempt_id, "start", f"OBS-{attempt_id}-START", instance=f"runtime-{attempt_id}")
        record_runtime_event(control, "design-run", "owner-a", paths, attempt_id, "stop", f"OBS-{attempt_id}-STOP", instance=f"runtime-{attempt_id}", descendant_writers="included")
        current, _ = ledger.load_state(paths)
        run("ingest-return", "--control-root", str(control), "--run-id", "design-run", "--owner-token", "owner-a", "--revision", str(current["revision"]), "--attempt-id", attempt_id, "--return-file", str(inbox), "--kind", "review")

    def test_happy_path_publication_reviews_and_gates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); control, _, _ = self.setup_g1(root); bundle = self.bundle(root, control)
            published = json.loads(self.publish(control, bundle).stdout)
            self.assertEqual(3, published["revision"])
            paths = ledger.paths(control, "design-run")
            state, _ = ledger.load_state(paths); ledger.validate_ledger(state)
            self.assertEqual(6, len(state["design_publication"]["document_refs"]))
            self.assertEqual("ACTIVE", state["lifecycle"]["control"])
            same = json.loads(self.publish(control, bundle, revision=3).stdout)
            self.assertTrue(same["idempotent"]); self.assertEqual(3, same["revision"])
            packet = self.review_packet(root, control, "A-coverage", "coverage", source_revision=3)
            self.prepare_review(control, packet, "A-coverage", "coverage", 3); self.finish_review(root, control, "A-coverage", 4)
            packet = self.review_packet(root, control, "A-plan", "plan", source_revision=5)
            self.prepare_review(control, packet, "A-plan", "plan", 5); self.finish_review(root, control, "A-plan", 6)
            state, _ = ledger.load_state(paths)
            run("gate", "--control-root", str(control), "--run-id", "design-run", "--owner-token", "owner-a", "--revision", str(state["revision"]), "--phase", "DESIGN", "--control", "ACTIVE", "--gate-id", "G2", "--next-action", "g2_pass")
            state, _ = ledger.load_state(paths)
            run("gate", "--control-root", str(control), "--run-id", "design-run", "--owner-token", "owner-a", "--revision", str(state["revision"]), "--phase", "PLAN", "--control", "ACTIVE", "--gate-id", "G3", "--next-action", "g3_pass")
            final, _ = ledger.load_state(paths)
            self.assertEqual("PLAN", final["lifecycle"]["phase"])
            self.assertEqual({"coverage", "plan"}, {item["review_kind"] for item in final["reviews"]})
            self.assertTrue(all(item["reviewer_identity"] and item["reviewer_role"] for item in final["reviews"]))

    def test_gate_id_is_explicit_and_next_action_text_cannot_claim_g3(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, _, _ = self.setup_g1(root)
            self.publish(control, self.bundle(root, control))
            self.prepare_review(
                control, self.review_packet(root, control, "A-coverage-only", "coverage", source_revision=3),
                "A-coverage-only", "coverage", 3,
            )
            self.finish_review(root, control, "A-coverage-only", 4)
            state, raw_before = ledger.load_state(ledger.paths(control, "design-run"))
            self.assertFalse(ledger.design_review_pass(state, "plan"))

            guessed = run(
                "gate", "--control-root", str(control), "--run-id", "design-run", "--owner-token", "owner-a",
                "--revision", str(state["revision"]), "--phase", "PLAN", "--control", "ACTIVE",
                "--next-action", "G3 plan PASS (untrusted descriptive text)", expect=2,
            )
            self.assertRegex(guessed.stderr.lower(), r"gate.?id|explicit")
            unchanged, raw_after_guess = ledger.load_state(ledger.paths(control, "design-run"))
            self.assertEqual(state["revision"], unchanged["revision"])
            self.assertEqual(raw_before, raw_after_guess)

            rejected_g3 = run(
                "gate", "--control-root", str(control), "--run-id", "design-run", "--owner-token", "owner-a",
                "--revision", str(state["revision"]), "--phase", "PLAN", "--control", "ACTIVE",
                "--gate-id", "G3", "--next-action", "ordinary inspection text", expect=2,
            )
            self.assertIn("G3", rejected_g3.stderr)
            self.assertIn("plan", rejected_g3.stderr.lower())
            unchanged, raw_after_rejection = ledger.load_state(ledger.paths(control, "design-run"))
            self.assertEqual(state["revision"], unchanged["revision"])
            self.assertEqual(raw_before, raw_after_rejection)

    def test_blocked_design_to_plan_requires_g3_but_same_phase_recovery_does_not(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, _, _ = self.setup_g1(root)
            paths = ledger.paths(control, "design-run")
            state, raw_before = ledger.load_state(paths)
            self.assertEqual("DESIGN", state["lifecycle"]["phase"])
            self.assertEqual("BLOCKED", state["lifecycle"]["control"])

            guessed = run(
                "gate", "--control-root", str(control), "--run-id", "design-run", "--owner-token", "owner-a",
                "--revision", str(state["revision"]), "--phase", "PLAN", "--control", "ACTIVE",
                "--next-action", "G3 coverage and plan PASS", expect=2,
            )
            self.assertRegex(guessed.stderr.lower(), r"gate.?id|explicit|g3")
            unchanged, raw_after = ledger.load_state(paths)
            self.assertEqual(state["revision"], unchanged["revision"])
            self.assertEqual(raw_before, raw_after)

            explicit_without_evidence = run(
                "gate", "--control-root", str(control), "--run-id", "design-run", "--owner-token", "owner-a",
                "--revision", str(state["revision"]), "--phase", "PLAN", "--control", "ACTIVE",
                "--gate-id", "G3", "--next-action", "ordinary descriptive text", expect=2,
            )
            self.assertRegex(explicit_without_evidence.stderr.lower(), r"publication|coverage|plan|pass|review|design bundle")
            unchanged, raw_after = ledger.load_state(paths)
            self.assertEqual(state["revision"], unchanged["revision"])
            self.assertEqual(raw_before, raw_after)

            # Resuming the blocked DESIGN phase is not a gate edge and must not
            # require G2 or G3 evidence just to continue owner work.
            recovered = run(
                "gate", "--control-root", str(control), "--run-id", "design-run", "--owner-token", "owner-a",
                "--revision", str(state["revision"]), "--phase", "DESIGN", "--control", "ACTIVE",
                "--next-action", "continue_design_recovery",
            )
            self.assertEqual("ACTIVE", json.loads(recovered.stdout)["control"])
            final, _ = ledger.load_state(paths)
            self.assertEqual("DESIGN", final["lifecycle"]["phase"])
            self.assertEqual("ACTIVE", final["lifecycle"]["control"])

    def test_blocked_design_review_can_publish_revised_immutable_publication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); control, _, _ = self.setup_g1(root); bundle_v2 = self.bundle(root, control)
            self.publish(control, bundle_v2)
            paths = ledger.paths(control, "design-run")
            packet = self.review_packet(root, control, "A-v2-coverage", "coverage", source_revision=3)
            self.prepare_review(control, packet, "A-v2-coverage", "coverage", 3)
            self.finish_review(root, control, "A-v2-coverage", 4, verdict="BLOCK")
            blocked, _ = ledger.load_state(paths)
            self.assertEqual("BLOCKED", blocked["lifecycle"]["control"])
            self.assertEqual("released", next(a for a in blocked["attempts"] if a["id"] == "A-v2-coverage")["lease"]["state"])

            value = json.loads(bundle_v2.read_text(encoding="utf-8"))
            value["bundle_id"] = "B-design-v3"
            value["version"] = "v3"
            revised_source = root / "D-design-v3.md"
            revised_source.write_text("# D-design-v3\n\nrevised design\n", encoding="utf-8")
            value["documents"][0] = {**value["documents"][0], "id": "D-design-v3", "version": "v3", "source": str(revised_source), "hash": ledger.sha256_file(revised_source)}
            bundle_v3 = root / "B-design-v3.json"; write_json(bundle_v3, value)
            state, _ = ledger.load_state(ledger.paths(control, "design-run"))
            published = json.loads(self.publish(control, bundle_v3, revision=state["revision"]).stdout)
            self.assertFalse(published["idempotent"])
            self.assertEqual(state["revision"] + 1, published["revision"])

            state, _ = ledger.load_state(paths)
            history = state["design_publication_history"]
            self.assertEqual(["B-design-v1", "B-design-v3"], [item["id"] for item in history])
            self.assertEqual("SUPERSEDED", history[0]["status"])
            self.assertEqual("B-design-v3", history[0]["superseded_by"])
            self.assertEqual("PUBLISHED", state["design_publication"]["status"])
            self.assertEqual("B-design-v3", state["design_publication"]["id"])
            self.assertEqual("ACTIVE", state["lifecycle"]["control"])
            self.assertEqual("BLOCK", state["reviews"][0]["verdict"])
            self.assertFalse([issue for issue in state.get("issues", []) if issue.get("impact") == "blocking"])
            retry = json.loads(self.publish(control, bundle_v3, revision=published["revision"] - 1).stdout)
            self.assertTrue(retry["idempotent"])
            self.assertEqual(2, len(ledger.load_state(paths)[0]["design_publication_history"]))

            fresh_packet = self.review_packet(root, control, "A-v3-coverage", "coverage", source_revision=6)
            self.prepare_review(control, fresh_packet, "A-v3-coverage", "coverage", 6)
            self.finish_review(root, control, "A-v3-coverage", 7)
            state, _ = ledger.load_state(paths)
            self.assertEqual("B-design-v3", state["design_publication"]["id"])
            self.assertTrue(ledger.design_review_pass(state, "coverage"))
            self.assertEqual(2, len({item["subject_fingerprint"] for item in state["reviews"]}))
            run("gate", "--control-root", str(control), "--run-id", "design-run", "--owner-token", "owner-a", "--revision", str(state["revision"]), "--phase", "DESIGN", "--control", "ACTIVE", "--gate-id", "G2", "--next-action", "g2_pass")

    def test_unverifiable_review_is_terminal_and_releases_lease(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); control, _, _ = self.setup_g1(root); bundle = self.bundle(root, control)
            self.publish(control, bundle)
            packet = self.review_packet(root, control, "A-unverifiable", "coverage", source_revision=3)
            self.prepare_review(control, packet, "A-unverifiable", "coverage", 3)
            self.finish_review(root, control, "A-unverifiable", 4, verdict="UNVERIFIABLE")
            state, _ = ledger.load_state(ledger.paths(control, "design-run"))
            attempt = ledger.attempt_by_id(state, "A-unverifiable")
            self.assertEqual("RETURNED", attempt["state"])
            self.assertEqual("UNVERIFIABLE", attempt["review_result"])
            self.assertEqual("released", attempt["lease"]["state"])

    def test_plan_block_returns_to_design_for_republish_but_execution_does_not(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); control, _, _ = self.setup_g1(root); bundle_v2 = self.bundle(root, control)
            self.publish(control, bundle_v2)
            packet = self.review_packet(root, control, "A-coverage", "coverage", source_revision=3)
            self.prepare_review(control, packet, "A-coverage", "coverage", 3); self.finish_review(root, control, "A-coverage", 4)
            paths = ledger.paths(control, "design-run"); state, _ = ledger.load_state(paths)
            run("gate", "--control-root", str(control), "--run-id", "design-run", "--owner-token", "owner-a", "--revision", str(state["revision"]), "--phase", "PLAN", "--control", "BLOCKED", "--reason", "plan_review_block", "--next-action", "plan-review")
            state, _ = ledger.load_state(paths)
            packet = self.review_packet(root, control, "A-plan-block", "plan", source_revision=state["revision"])
            self.prepare_review(control, packet, "A-plan-block", "plan", state["revision"])
            self.finish_review(root, control, "A-plan-block", state["revision"] + 1, verdict="BLOCK")
            state, _ = ledger.load_state(paths)
            run("gate", "--control-root", str(control), "--run-id", "design-run", "--owner-token", "owner-a", "--revision", str(state["revision"]), "--phase", "DESIGN", "--control", "BLOCKED", "--reason", "design_revision_required", "--next-action", "publish-design-bundle")
            state, _ = ledger.load_state(paths)
            self.assertEqual("DESIGN", state["lifecycle"]["phase"])
            value = json.loads(bundle_v2.read_text(encoding="utf-8")); value["bundle_id"] = "B-design-v3"; value["version"] = "v3"
            revised_source = root / "D-design-v3.md"; revised_source.write_text("# revised\n", encoding="utf-8")
            value["documents"][0] = {**value["documents"][0], "id": "D-design-v3", "version": "v3", "source": str(revised_source), "hash": ledger.sha256_file(revised_source)}
            bundle_v3 = root / "B-design-v3.json"; write_json(bundle_v3, value)
            self.publish(control, bundle_v3, revision=state["revision"])
            state, _ = ledger.load_state(paths)
            state["lifecycle"]["phase"] = "EXECUTE"; state["lifecycle"]["control"] = "BLOCKED"; state["lifecycle"]["reason"] = "implementation_block"
            ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
            value["bundle_id"] = "B-design-v4"; value["version"] = "v4"; bundle_v4 = root / "B-design-v4.json"; write_json(bundle_v4, value)
            rejected = self.publish(control, bundle_v4, revision=state["revision"], expect=2)
            self.assertIn("DESIGN", rejected.stderr)

    def test_failure_safety_and_conflict_rejection(self) -> None:
        cases = ("missing", "malformed", "stale", "wrong-owner", "wrong-epoch", "traversal", "partial", "canonical-conflict")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); control, _, _ = self.setup_g1(root); bundle = self.bundle(root, control)
                original = ledger.paths(control, "design-run")["ledger"].read_bytes()
                value = json.loads(bundle.read_text(encoding="utf-8"))
                if case == "missing":
                    value["documents"][0]["source"] = str(root / "does-not-exist.md")
                elif case == "malformed":
                    value["documents"][0]["hash"] = "0" * 64
                elif case == "stale":
                    value["intent_revision"] = "intent-v1"
                elif case == "wrong-epoch":
                    value["epoch"] = 1
                elif case == "traversal":
                    value["documents"][0]["source"] = str(root / ".." / "outside.md")
                elif case == "partial":
                    value["routes"] = []
                elif case == "canonical-conflict":
                    path = root / "D-design.md"
                    destination = ledger.canonical_document_path(ledger.paths(control, "design-run"), "D-design", "v1")
                    ledger.atomic_write(destination, b"# conflicting orphan\n")
                write_json(bundle, value)
                args = ["publish-design-bundle", "--control-root", str(control), "--run-id", "design-run", "--owner-token", "owner-a", "--revision", "2", "--bundle", str(bundle)]
                if case == "wrong-owner": args[args.index("owner-a")] = "owner-b"
                rejected = run(*args, expect=2)
                self.assertTrue(rejected.stderr)
                self.assertEqual(original, ledger.paths(control, "design-run")["ledger"].read_bytes())

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); control, _, _ = self.setup_g1(root); bundle = self.bundle(root, control)
            self.publish(control, bundle)
            conflicting = json.loads(bundle.read_text(encoding="utf-8")); conflicting["bundle_id"] = "B-design-v2"; write_json(bundle, conflicting)
            rejected = self.publish(control, bundle, revision=3, expect=2)
            self.assertIn("conflicting design bundle", rejected.stderr)
            state, _ = ledger.load_state(ledger.paths(control, "design-run")); self.assertEqual(3, state["revision"])

    def test_orphan_recovery_and_review_registration_after_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); control, _, _ = self.setup_g1(root); bundle = self.bundle(root, control)
            value = json.loads(bundle.read_text(encoding="utf-8"))
            paths = ledger.paths(control, "design-run")
            for document in value["documents"]:
                destination = ledger.canonical_document_path(paths, document["id"], document["version"])
                ledger.atomic_write(destination, Path(document["source"]).read_bytes())
            self.publish(control, bundle)
            recovered = json.loads(run("recover", "--control-root", str(control), "--run-id", "design-run", "--owner-token", "owner-a", "--revision", "3").stdout)
            self.assertEqual("RECOVERING", recovered["control"])
            state, _ = ledger.load_state(paths); self.assertEqual("PUBLISHED", state["design_publication"]["status"])
            run("gate", "--control-root", str(control), "--run-id", "design-run", "--owner-token", "owner-a", "--revision", str(state["revision"]), "--phase", "DESIGN", "--control", "ACTIVE", "--next-action", "resume_design_review")
            state, _ = ledger.load_state(paths)
            packet = self.review_packet(root, control, "A-recovered", "coverage", source_revision=state["revision"])
            self.prepare_review(control, packet, "A-recovered", "coverage", state["revision"])
            final, _ = ledger.load_state(paths)
            self.assertEqual("PREPARED", next(item for item in final["attempts"] if item["id"] == "A-recovered")["state"])

    def test_legacy_ledger_without_publication_metadata_remains_readable_but_recovery_is_fenced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); control, _, _ = self.setup_g1(root); paths = ledger.paths(control, "design-run")
            state, _ = ledger.load_state(paths); state["skill_version"] = "1.0.1"; state.pop("runtime_provenance", None); state.pop("design_publication", None); ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
            run("validate", "--file", str(paths["ledger"]), "--kind", "ledger")
            original = paths["ledger"].read_bytes()
            diagnostic = json.loads(run("diagnose", "--control-root", str(control), "--run-id", "design-run").stdout)
            self.assertTrue(diagnostic["readable"])
            self.assertFalse(diagnostic["mutation_eligible"])
            resumed = run("recover", "--control-root", str(control), "--run-id", "design-run", "--owner-token", "owner-a", "--revision", str(state["revision"]), expect=2)
            self.assertIn("mutation is read-only", resumed.stderr)
            self.assertEqual(original, paths["ledger"].read_bytes())

    def test_mixed_review_kinds_are_not_disagreement_and_state_preflight_matches_ingest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); control, _, _ = self.setup_g1(root); bundle = self.bundle(root, control)
            self.publish(control, bundle)
            paths = ledger.paths(control, "design-run")
            packet = self.review_packet(root, control, "A-coverage-mixed", "coverage", source_revision=3)
            self.prepare_review(control, packet, "A-coverage-mixed", "coverage", 3)
            self.finish_review(root, control, "A-coverage-mixed", 4, verdict="PASS")
            packet = self.review_packet(root, control, "A-plan-mixed", "plan", source_revision=5)
            self.prepare_review(control, packet, "A-plan-mixed", "plan", 5)
            state, _ = ledger.load_state(paths); attempt = next(item for item in state["attempts"] if item["id"] == "A-plan-mixed")
            returned = {"identity": {"run_id": "design-run", "attempt_id": "A-plan-mixed", "packet_hash": attempt["packet_hash"], "epoch": 0, "source_revision": attempt["packet_source_revision"], "registration_revision": attempt["packet_registration_revision"], "subject_revision": attempt["subject_revision"], "intent_revision": "intent-v2"}, "subject_fingerprint": state["design_publication"]["publication_hash"], "verdict": "BLOCK", "coverage": [{"criterion_id": "C-1", "outcome": "unverifiable", "evidence_refs": ["EV-plan"]}], "checks": [{"check_id": "plan-check", "axis": "wrong-axis", "outcome": "not_run", "actual": "blocked", "evidence_ref": "EV-plan"}], "context_refs": ["clean"], "findings": []}
            inbox = paths["scratch"] / "A-plan-mixed" / "return.json"; write_json(inbox, returned)
            original = paths["ledger"].read_bytes()
            preflight = run("validate-return", "--control-root", str(control), "--run-id", "design-run", "--attempt-id", "A-plan-mixed", "--return-file", str(inbox), "--kind", "review", expect=2)
            self.assertIn("axes do not exactly match", preflight.stderr); self.assertEqual(original, paths["ledger"].read_bytes())
            returned["checks"][0]["axis"] = "plan"; write_json(inbox, returned)
            run("validate-return", "--control-root", str(control), "--run-id", "design-run", "--attempt-id", "A-plan-mixed", "--return-file", str(inbox), "--kind", "review")
            record_runtime_event(control, "design-run", "owner-a", paths, "A-plan-mixed", "start", "OBS-A-plan-mixed-START", instance="runtime-A-plan-mixed")
            record_runtime_event(control, "design-run", "owner-a", paths, "A-plan-mixed", "stop", "OBS-A-plan-mixed-STOP", instance="runtime-A-plan-mixed", descendant_writers="included")
            current, _ = ledger.load_state(paths)
            run("ingest-return", "--control-root", str(control), "--run-id", "design-run", "--owner-token", "owner-a", "--revision", str(current["revision"]), "--attempt-id", "A-plan-mixed", "--return-file", str(inbox), "--kind", "review")
            state, _ = ledger.load_state(paths)
            self.assertFalse([item for item in state.get("issues", []) if item.get("type") == "reviewer_disagreement"])
            self.assertEqual("review_not_pass", state["lifecycle"]["reason"])
            self.assertEqual("released", ledger.attempt_by_id(state, "A-plan-mixed")["lease"]["state"])

    def test_supersession_fences_findings_even_when_not_in_lifecycle_issue_refs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); control, _, _ = self.setup_g1(root); bundle = self.bundle(root, control); self.publish(control, bundle)
            paths = ledger.paths(control, "design-run")
            packet = self.review_packet(root, control, "A-finding", "coverage", source_revision=3); self.prepare_review(control, packet, "A-finding", "coverage", 3)
            state, _ = ledger.load_state(paths); attempt = ledger.attempt_by_id(state, "A-finding")
            returned = {"identity": {"run_id": "design-run", "attempt_id": "A-finding", "packet_hash": attempt["packet_hash"], "epoch": 0, "source_revision": attempt["packet_source_revision"], "intent_revision": "intent-v2"}, "subject_fingerprint": state["design_publication"]["publication_hash"], "verdict": "BLOCK", "coverage": [{"criterion_id": "C-1", "outcome": "missing", "evidence_refs": ["EV"]}], "checks": [{"check_id": "coverage", "axis": "coverage", "outcome": "failed", "actual": "missing", "evidence_ref": "EV"}], "context_refs": ["clean"], "findings": [{"axis": "coverage", "impact": "blocking", "claim": "missing ownership", "expected": "owned", "actual": "missing", "evidence": "EV", "affected_refs": ["coverage"]}]}
            inbox = paths["scratch"] / "A-finding" / "return.json"; write_json(inbox, returned)
            record_runtime_event(control, "design-run", "owner-a", paths, "A-finding", "start", "OBS-A-finding-START", instance="runtime-A-finding")
            record_runtime_event(control, "design-run", "owner-a", paths, "A-finding", "stop", "OBS-A-finding-STOP", instance="runtime-A-finding", descendant_writers="included")
            current, _ = ledger.load_state(paths)
            run("ingest-return", "--control-root", str(control), "--run-id", "design-run", "--owner-token", "owner-a", "--revision", str(current["revision"]), "--attempt-id", "A-finding", "--return-file", str(inbox), "--kind", "review")
            state, _ = ledger.load_state(paths); state["lifecycle"]["issue_refs"] = [ref for ref in state["lifecycle"]["issue_refs"] if not ref.startswith("issue-")]; ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
            value = json.loads(bundle.read_text(encoding="utf-8")); value["bundle_id"] = "B-design-v2"; value["version"] = "v2"; source = root / "D-design-v2.md"; source.write_text("# revised\n", encoding="utf-8"); value["documents"][0] = {**value["documents"][0], "id": "D-design-v2", "version": "v2", "source": str(source), "hash": ledger.sha256_file(source)}; revised = root / "revised.json"; write_json(revised, value)
            current, _ = ledger.load_state(paths)
            self.publish(control, revised, revision=current["revision"])
            final, _ = ledger.load_state(paths)
            old_finding = final["findings"][0]
            self.assertIn("B-design-v2", old_finding["invalidated_by"])
            linked = [item for item in final["issues"] if item.get("finding_ref") == old_finding["id"]]
            self.assertTrue(linked); self.assertTrue(all(item["impact"] == "advisory" for item in linked))

    def test_amendment_invalidates_design_binding_and_old_reviews(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); control, _, _ = self.setup_g1(root); bundle = self.bundle(root, control)
            self.publish(control, bundle)
            amended = root / "intent-v3.md"; amended.write_text("# Amended product intent\n", encoding="utf-8")
            run("amend", "--control-root", str(control), "--run-id", "design-run", "--owner-token", "owner-a", "--revision", "3", "--intent-file", str(amended), "--doc-id", "D-intent-v3", "--doc-version", "v3", "--intent-revision", "intent-v3", "--amendment-id", "AM-design", "--authority-ref", "user-message")
            state, _ = ledger.load_state(ledger.paths(control, "design-run"))
            self.assertEqual("INVALIDATED", state["design_publication"]["status"])
            self.assertIn("AM-design", state["design_publication"]["invalidated_by"])
            with self.assertRaises(ledger.LedgerError):
                ledger.current_design_publication(state)
            ledger.validate_ledger(state)

    def test_self_produced_proposed_contract_is_rejected_before_design_gates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); control, _, _ = self.setup_g1(root); bundle = self.bundle(root, control)
            value = json.loads(bundle.read_text(encoding="utf-8"))
            value["contracts"][0]["status"] = "proposed"
            value["contracts"][0]["producer_refs"] = ["T-design"]
            write_json(bundle, value)

            rejected = self.publish(control, bundle, expect=2)

            self.assertIn("requires self-produced contract", rejected.stderr)
            state, _ = ledger.load_state(ledger.paths(control, "design-run"))
            self.assertIsNone(state.get("design_publication"))
            self.assertEqual("DESIGN", state["lifecycle"]["phase"])

            value["tickets"][0]["contract_refs"] = []
            write_json(bundle, value)
            published = json.loads(self.publish(control, bundle).stdout)
            self.assertEqual(3, published["revision"])
            current, _ = ledger.load_state(ledger.paths(control, "design-run"))
            contract = next(item for item in current["contracts"] if item["id"] == "K-design")
            self.assertEqual("proposed", contract["status"])

    def test_external_inactive_input_remains_a_ready_ticket_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); control, _, _ = self.setup_g1(root); bundle = self.bundle(root, control)
            value = json.loads(bundle.read_text(encoding="utf-8"))
            value["contracts"][0]["status"] = "proposed"
            value["contracts"][0]["producer_refs"] = []
            write_json(bundle, value)
            self.publish(control, bundle)
            paths = ledger.paths(control, "design-run")
            state, previous = ledger.load_state(paths)
            state["lifecycle"] = {"phase": "EXECUTE", "control": "ACTIVE", "reason": None, "issue_refs": [], "stop_target": None, "next_action": {"kind": "ready-ticket", "subject_refs": ["T-design"], "preconditions": [], "read_refs": []}}
            state["revision"] += 1
            state["previous_publication_hash"] = ledger.sha256_bytes(previous)
            ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))

            rejected = run("ready-ticket", "--control-root", str(control), "--run-id", "design-run", "--owner-token", "owner-a", "--revision", str(state["revision"]), "--ticket-id", "T-design", expect=2)

            self.assertIn("no current accepted contract input", rejected.stderr)
            unchanged, _ = ledger.load_state(paths)
            self.assertEqual("PLANNED", unchanged["tickets"][0]["state"])

    def test_legacy_mixed_publication_is_not_silently_reinterpreted_at_g2(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); control, _, _ = self.setup_g1(root); bundle = self.bundle(root, control)
            value = json.loads(bundle.read_text(encoding="utf-8"))
            value["contracts"][0]["status"] = "proposed"
            value["contracts"][0]["producer_refs"] = ["T-design"]
            value["tickets"][0]["contract_refs"] = []
            write_json(bundle, value)
            self.publish(control, bundle)
            paths = ledger.paths(control, "design-run")
            state, _ = ledger.load_state(paths)
            ticket = next(item for item in state["tickets"] if item["id"] == "T-design")
            ticket["contract_refs"] = ["K-design"]  # Simulate a mixed bundle published by an older helper.
            ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))

            rejected = run("gate", "--control-root", str(control), "--run-id", "design-run", "--owner-token", "owner-a", "--revision", str(state["revision"]), "--phase", "DESIGN", "--control", "ACTIVE", "--gate-id", "G2", "--next-action", "g2_pass", expect=2)

            self.assertIn("requires self-produced contract", rejected.stderr)
            unchanged, _ = ledger.load_state(paths)
            self.assertEqual("proposed", next(item for item in unchanged["contracts"] if item["id"] == "K-design")["status"])


if __name__ == "__main__":
    unittest.main()
