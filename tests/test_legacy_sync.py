import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SYNC_PATH = ROOT / "upstream" / "autopilot" / "tools" / "sync.py"
SPEC = importlib.util.spec_from_file_location("legacy_sync", SYNC_PATH)
assert SPEC and SPEC.loader
sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync)


def write_state(path: Path, state: dict) -> None:
    path.write_text("window.STATE =\n" + json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def state_for(root: Path, statuses: dict[str, str], *, finished: bool) -> dict:
    return {
        "dir": "run",
        "runStatus": "done" if finished else "paused",
        "finishedAt": "2026-09-14T02:00:00+03:00" if finished else None,
        "updatedAt": "2026-09-14T01:59:40+03:00",
        "stages": [],
        "tickets": [{"id": ticket_id, "status": status} for ticket_id, status in statuses.items()],
    }


class LegacySyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.autopilot = self.root / ".autopilot"
        self.ticket_root = self.autopilot / "run" / "tickets"
        self.ticket_root.mkdir(parents=True)
        (self.autopilot / "dashboard.html").write_text("/*STATE-BEGIN*/old/*STATE-END*/", encoding="utf-8")
        self.state_path = self.autopilot / "state.js"
        self.pid_path = self.autopilot / "serve.pid"
        self.log_path = self.autopilot / "serve.log"
        self.old_constants = {name: getattr(sync, name) for name in ("A", "STATE", "PAGE", "PIDF", "LOG")}
        sync.A = str(self.autopilot)
        sync.STATE = str(self.state_path)
        sync.PAGE = str(self.autopilot / "dashboard.html")
        sync.PIDF = str(self.pid_path)
        sync.LOG = str(self.log_path)

    def tearDown(self) -> None:
        for name, value in self.old_constants.items():
            setattr(sync, name, value)
        self.temp.cleanup()

    def add_tickets(self, statuses: dict[str, str]) -> None:
        for ticket_id in statuses:
            (self.ticket_root / f"{ticket_id}-ticket.md").write_text(
                f"# {ticket_id} — fixture\n\n**Status:** ready\n\nBody\n", encoding="utf-8"
            )

    def artifact_status(self, ticket_id: str) -> str:
        text = (self.ticket_root / f"{ticket_id}-ticket.md").read_text(encoding="utf-8")
        return next(line.split()[-1] for line in text.splitlines() if line.startswith("**Status:**"))

    def run_main(self, no_serve: bool = True) -> None:
        argv = ["sync.py"] + (["--no-serve"] if no_serve else [])
        with mock.patch.object(sys, "argv", argv):
            sync.main()

    def test_integrated_ticket_updates_canonical_artifact(self) -> None:
        statuses = {"01": "done", "02": "done", "03": "done"}
        self.add_tickets(statuses)
        write_state(self.state_path, state_for(self.root, statuses, finished=True))

        self.run_main()

        self.assertEqual({ticket_id: "done" for ticket_id in statuses}, {ticket_id: self.artifact_status(ticket_id) for ticket_id in statuses})
        self.assertIn("window.STATE=", (self.autopilot / "dashboard.html").read_text(encoding="utf-8"))

    def test_multiple_tickets_remain_synced_across_pause_resume(self) -> None:
        paused = {"01": "done", "02": "done", "03": "in-progress"}
        self.add_tickets(paused)
        write_state(self.state_path, state_for(self.root, paused, finished=False))
        self.run_main()
        self.assertEqual("done", self.artifact_status("01"))
        self.assertEqual("done", self.artifact_status("02"))
        self.assertEqual("in-progress", self.artifact_status("03"))

        resumed = {"01": "done", "02": "done", "03": "done"}
        write_state(self.state_path, state_for(self.root, resumed, finished=True))
        self.run_main()
        self.assertEqual({ticket_id: "done" for ticket_id in resumed}, {ticket_id: self.artifact_status(ticket_id) for ticket_id in resumed})

    def test_terminal_run_stops_dashboard_and_repeated_finalization_is_safe(self) -> None:
        statuses = {"01": "done"}
        self.add_tickets(statuses)
        write_state(self.state_path, state_for(self.root, statuses, finished=True))
        self.pid_path.write_text("8765 123\n", encoding="utf-8")

        with mock.patch.object(sync, "stop_dashboard") as stop:
            self.run_main(no_serve=True)
            self.run_main(no_serve=False)
        self.assertEqual(2, stop.call_count)

    def test_dashboard_match_requires_exact_directory_and_module(self) -> None:
        self.assertTrue(sync.is_ours(f"/usr/bin/python3 -m http.server 8765 --directory {self.autopilot}"))
        self.assertFalse(sync.is_ours(f"/usr/bin/python3 -m http.server 8765 --directory {self.autopilot}-other"))
        self.assertFalse(sync.is_ours(f"/usr/bin/python3 -m http-server 8765 --directory {self.autopilot}"))

    def test_stop_dashboard_verifies_termination_before_cleanup(self) -> None:
        self.pid_path.write_text("8765 101\n", encoding="utf-8")
        running = {101: True}

        def still_running(pid: int) -> bool:
            was_running = running[pid]
            running[pid] = False
            return was_running

        with mock.patch.object(sync, "owned_pids", return_value=[101]), mock.patch.object(sync, "process_running", side_effect=still_running), mock.patch.object(sync.os, "kill") as kill:
            stopped = sync.stop_dashboard(grace=0)

        self.assertEqual([101], stopped)
        self.assertEqual([mock.call(101, sync.signal.SIGTERM)], kill.call_args_list)
        self.assertFalse(self.pid_path.exists())

    def test_missing_stale_and_already_dead_pid_are_noops(self) -> None:
        for contents in (None, "8765 999999\n", "not-a-pid\n"):
            if contents is None:
                self.pid_path.unlink(missing_ok=True)
            else:
                self.pid_path.write_text(contents, encoding="utf-8")
            with mock.patch.object(sync, "owned_pids", return_value=[]):
                self.assertEqual([], sync.stop_dashboard(grace=0))
            self.assertFalse(self.pid_path.exists())


if __name__ == "__main__":
    unittest.main()
