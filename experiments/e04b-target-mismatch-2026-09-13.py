#!/usr/bin/env python3
"""The one remaining E04b target-mismatch arm."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from v1_final_qualification import fresh, ledger, run, write_json  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="codex-autopilot-e04b-target-") as directory:
        root = Path(directory)
        control, repo, run_id = fresh(root, "E04b-target", phase="EXECUTE")
        prepared = run("prepare-effect", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-a", "--revision", "1", "--operation-id", "OP-target", "--kind", "candidate_commit", "--target", str(repo), "--authority-ref", "E04b")
        wrong = root / "wrong-receipt.json"
        write_json(wrong, {"operation_id": "OP-target", "target": str(root / "other-repo"), "status": "PASS", "result": "wrong target"})
        rejected = run("reconcile-effect", "--control-root", str(control), "--run-id", run_id, "--owner-token", "owner-a", "--revision", "2", "--operation-id", "OP-target", "--result", "applied", "--receipt", str(wrong), expect=2)
        state, _ = ledger.load_state(ledger.paths(control, run_id))
        operation = state["operations"][0]
        result = {"experiment": "E04b-target-mismatch", "prepared": prepared, "rejected": rejected, "operation_after": operation, "revision_after": state["revision"], "qualified": prepared["matched_expected"] and rejected["matched_expected"] and "target mismatch" in rejected["stderr"] and operation["state"] == "prepared" and state["revision"] == 2}
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
