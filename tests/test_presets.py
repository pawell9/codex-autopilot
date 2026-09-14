import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools import dashboard, ledger


ROOT = Path(__file__).resolve().parents[1]
CLI = ["python3", str(ROOT / "tools" / "ledger.py")]


def run(*args: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run([*CLI, *args], text=True, capture_output=True)
    if result.returncode != expect:
        raise AssertionError(f"expected {expect}, got {result.returncode}: {result.stdout}\n{result.stderr}")
    return result


class PresetTests(unittest.TestCase):
    def init_run(self, root: Path, request: str | None = None) -> tuple[Path, Path, str]:
        control, repo = root / "control", root / "repo"
        control.mkdir(); repo.mkdir()
        args = ["init", "--control-root", str(control), "--repo-root", str(repo), "--run-id", "run", "--owner-token", "owner"]
        if request:
            args += ["--request", request]
        run(*args)
        return control, repo, "run"

    def test_defaults_semi_normal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            control, _, run_id = self.init_run(Path(directory), "codex-autopilot — сделай безопасное изменение")
            state, _ = ledger.load_state(ledger.paths(control, run_id))
            self.assertEqual({"interaction_mode": "semi", "depth": "normal"}, state["run_settings"])
            self.assertEqual(ledger.DEFAULT_RUN_SETTINGS, ledger.parse_run_settings("codex-autopilot — сделай"))
            self.assertIn("полуавтомат", run("status", "--control-root", str(control), "--run-id", run_id).stdout)

    def test_explicit_full_deep_and_ambiguous_defaults(self) -> None:
        self.assertEqual({"interaction_mode": "full", "depth": "deep"}, ledger.parse_run_settings("codex-autopilot полный автомат, глубокая — сделай"))
        self.assertEqual({"interaction_mode": "full", "depth": "deep"}, ledger.parse_run_settings("full automatic, deep change"))
        self.assertEqual(ledger.DEFAULT_RUN_SETTINGS, ledger.parse_run_settings("полный автомат и полуавтомат; deep и normal"))

    def test_legacy_ledger_defaults_without_migration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            control, _, run_id = self.init_run(Path(directory))
            path = ledger.paths(control, run_id)["ledger"]
            state, _ = ledger.load_state(ledger.paths(control, run_id))
            del state["run_settings"]
            ledger.atomic_write(path, ledger.canonical_bytes(state))
            loaded, _ = ledger.load_state(ledger.paths(control, run_id))
            self.assertNotIn("run_settings", loaded)
            self.assertEqual(ledger.DEFAULT_RUN_SETTINGS, ledger.resolved_run_settings(loaded))

    def test_pause_resume_and_recovery_preserve_presets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            control, _, run_id = self.init_run(Path(directory), "полный автомат, deep — сделай")
            run("gate", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner", "--revision", "0", "--control", "QUIESCING")
            run("gate", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner", "--revision", "1", "--control", "PAUSED")
            run("recover", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner", "--revision", "2")
            run("gate", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner", "--revision", "3", "--phase", "PREFLIGHT", "--control", "ACTIVE")
            state, _ = ledger.load_state(ledger.paths(control, run_id))
            self.assertEqual({"interaction_mode": "full", "depth": "deep"}, state["run_settings"])

    def test_status_dashboard_and_routing_keep_resolved_presets_separate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            control, _, run_id = self.init_run(Path(directory), "full automatic, thorough — implement")
            state, raw = ledger.load_state(ledger.paths(control, run_id))
            status = json.loads(run("status", "--control-root", str(control), "--run-id", run_id).stdout)
            brief = json.loads(run("brief", "--control-root", str(control), "--run-id", run_id).stdout)
            projection = dashboard.project_ledger(state, ledger.paths(control, run_id)["ledger"], raw)
            self.assertEqual({"interaction_mode": "full", "depth": "deep"}, status["run_settings"])
            self.assertEqual(status["run_settings"], brief["run_settings"])
            self.assertEqual(status["run_settings"], projection["run_settings"])
            self.assertEqual("Режим: полный автомат · глубина: глубокая", projection["run"]["preset_display"])
            self.assertEqual({"interaction_mode": "full", "depth": "deep", "model_binding": None}, ledger.routing_intent(state))


if __name__ == "__main__":
    unittest.main()
