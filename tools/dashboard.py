#!/usr/bin/env python3
"""Read-only local dashboard for the current Codex Autopilot ledger.

The dashboard is deliberately a projection, not another state store.  Every
request reloads the selected canonical ``.autopilot/**/ledger.json`` and the
server exposes only GET endpoints.  It never publishes, locks, or rewrites a
ledger.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

try:
    from ledger import LedgerError, PHASES, load_state, paths, resolved_run_settings, run_settings_display, sha256_bytes
except ModuleNotFoundError:  # package import from tests/tools callers
    from .ledger import LedgerError, PHASES, load_state, paths, resolved_run_settings, run_settings_display, sha256_bytes


ROOT = Path(__file__).resolve().parents[1]
HTML_PATH = ROOT / "dashboard" / "index.html"
TERMINAL_CONTROLS = {"ACCEPTED", "FAILED", "CANCELLED"}
ACTIVE_ATTEMPT_STATES = {"PREPARED", "DISPATCHED"}
ACTIVE_LEASE_STATES = {"active"}
GATES = (
    ("G0", "PREFLIGHT", "Preflight"),
    ("G1", "INTENT", "Intent"),
    ("G2", "DESIGN", "Design"),
    ("G3", "PLAN", "Plan"),
    ("G4", "EXECUTE", "Execute"),
    ("G5", "VERIFY", "Verify"),
    ("G6", "ACCEPT", "Accept"),
)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _add_concern(concerns: list[dict[str, str]], code: str, message: str) -> None:
    concerns.append({"code": code, "message": message})


def _find_attempt(state: dict[str, Any], attempt_id: str | None) -> dict[str, Any] | None:
    if not attempt_id:
        return None
    return next((item for item in state.get("attempts", []) if item.get("id") == attempt_id), None)


def _candidate_records(state: dict[str, Any]) -> list[dict[str, Any]]:
    canonical = state.get("candidates")
    if isinstance(canonical, list) and canonical:
        attempts = {item.get("id"): item for item in state.get("attempts", []) if item.get("id")}
        records: list[dict[str, Any]] = []
        for candidate in canonical:
            if candidate.get("invalidated_by"):
                continue
            producer = attempts.get(candidate.get("producer_attempt_ref"), {})
            records.append({
                **candidate,
                "attempt_id": candidate.get("producer_attempt_ref"),
                "subject_ref": candidate.get("ticket_ref"),
                "state": producer.get("state"),
                "source": "candidate_record",
            })
        return records

    records: list[dict[str, Any]] = []
    for attempt in state.get("attempts", []):
        if attempt.get("invalidated_by"):
            continue
        sha = attempt.get("candidate_sha")
        tree_sha = attempt.get("candidate_tree_sha")
        if sha or tree_sha:
            records.append(
                {
                    "id": None,
                    "attempt_id": attempt.get("id"),
                    "subject_ref": attempt.get("subject_ref"),
                    "state": attempt.get("state"),
                    "sha": sha,
                    "tree_sha": tree_sha,
                    "source": "producer_attempt_fallback",
                }
            )
    return records


def _select_candidate(state: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not candidates:
        return None

    subject_refs = set(state.get("lifecycle", {}).get("next_action", {}).get("subject_refs", []))
    by_id = {candidate.get("id"): candidate for candidate in candidates if candidate.get("id")}
    current_pointers = [
        (ticket, by_id.get(ticket.get("current_candidate")))
        for ticket in state.get("tickets", [])
        if ticket.get("current_candidate")
    ]
    current_pointers = [(ticket, candidate) for ticket, candidate in current_pointers if candidate is not None]
    for ticket, candidate in current_pointers:
        if any(ref in subject_refs for ref in (
            ticket.get("id"), candidate.get("id"), candidate.get("producer_attempt_ref")
        )):
            return {**candidate, "source": "ticket.current_candidate", "ambiguous": False}
    if current_pointers:
        ticket, candidate = current_pointers[-1]
        return {**candidate, "source": "ticket.current_candidate", "ambiguous": len(current_pointers) > 1}

    canonical_candidates = [item for item in candidates if item.get("id")]
    if canonical_candidates:
        latest = next(
            (item for item in reversed(canonical_candidates) if not item.get("superseded_by")),
            canonical_candidates[-1],
        )
        return {**latest, "source": "candidate_record_fallback", "ambiguous": True}

    for candidate in candidates:
        if candidate.get("attempt_id") in subject_refs or candidate.get("subject_ref") in subject_refs:
            return {**candidate, "ambiguous": True}
    current_attempt_ids = {
        ticket.get("current_attempt") for ticket in state.get("tickets", [])
        if ticket.get("current_attempt")
    }
    for candidate in candidates:
        if candidate.get("attempt_id") in current_attempt_ids:
            return {**candidate, "ambiguous": True}

    # Pre-Phase-B attempt-only ledgers have no explicit candidate authority.
    return {**candidates[-1], "ambiguous": True}


def _project_gate_status(
    gate_index: int, current_index: int, control: str, state: dict[str, Any]
) -> tuple[str, str]:
    acceptances = state.get("acceptance", [])
    intent_revision = state.get("intent", {}).get("revision")
    if gate_index == 5 and any(
        item.get("verdict") == "PASS"
        and item.get("intent_revision") == intent_revision
        and not item.get("invalidated_by")
        for item in acceptances
    ):
        return "passed", "acceptance PASS"
    if gate_index == 6 and control == "ACCEPTED":
        return "passed", "lifecycle control ACCEPTED"
    if gate_index < current_index:
        return "reached", "lifecycle phase"
    if gate_index == current_index:
        if control == "BLOCKED":
            return "blocked", "lifecycle control BLOCKED"
        if control == "FAILED":
            return "failed", "lifecycle control FAILED"
        if control == "CANCELLED":
            return "cancelled", "lifecycle control CANCELLED"
        return "current", "lifecycle phase"
    return "pending", "lifecycle phase"


def project_ledger(state: dict[str, Any], ledger_path: Path, raw: bytes) -> dict[str, Any]:
    lifecycle = state.get("lifecycle", {})
    phase = lifecycle.get("phase")
    control = lifecycle.get("control")
    current_index = PHASES.index(phase) if phase in PHASES else -1
    concerns: list[dict[str, str]] = []

    # These are intentionally derived labels.  The canonical ledger schema
    # does not contain a mutable G0-G6 result collection.
    gates = []
    for index, (gate_id, gate_phase, label) in enumerate(GATES):
        status, basis = _project_gate_status(index, current_index, control, state)
        gates.append({"id": gate_id, "phase": gate_phase, "label": label, "status": status, "basis": basis})
    _add_concern(
        concerns,
        "gate-projection",
        "В ledger нет отдельной коллекции результатов G0–G6; статусы на экране — read-only projection из lifecycle и acceptance.",
    )

    tickets = []
    for ticket in state.get("tickets", []):
        tickets.append(
            {
                "id": ticket.get("id"),
                "status": ticket.get("state"),
                "goal_ref": ticket.get("goal_ref"),
                "current_attempt": ticket.get("current_attempt"),
            }
        )
    if "tickets" not in state:
        _add_concern(concerns, "tickets-missing", "В ledger отсутствует коллекция tickets; список tickets недоступен.")

    design_publication = state.get("design_publication")
    design_publication_history = state.get("design_publication_history", [])
    design_review_attempts = [
        {
            "id": attempt.get("id"),
            "kind": attempt.get("mode"),
            "state": attempt.get("state"),
            "result": attempt.get("review_result"),
            "reviewer_identity": attempt.get("reviewer_identity"),
            "reviewer_role": attempt.get("reviewer_role"),
            "target_revision": attempt.get("target_revision"),
        }
        for attempt in state.get("attempts", [])
        if attempt.get("mode") in ("coverage", "plan") and not attempt.get("invalidated_by")
    ]
    if phase in {"DESIGN", "PLAN"} and not design_publication:
        _add_concern(concerns, "design-publication-missing", "Для G2/G3 отсутствует canonical design publication; provisional artifacts не считаются опубликованными.")

    active = []
    for attempt in state.get("attempts", []):
        lease = attempt.get("lease", {})
        if attempt.get("state") in ACTIVE_ATTEMPT_STATES and lease.get("state") in ACTIVE_LEASE_STATES:
            active.append(
                {
                    "kind": attempt.get("kind"),
                    "attempt_id": attempt.get("id"),
                    "subject_ref": attempt.get("subject_ref"),
                    "state": attempt.get("state"),
                    "lease_id": lease.get("id"),
                    "route_ref": attempt.get("route_ref"),
                }
            )
    if active:
        _add_concern(
            concerns,
            "actor-identity",
            "В ledger нет actor/model identity; active worker/reviewer показаны по kind, attempt, subject и route IDs.",
        )

    candidates = _candidate_records(state)
    current_candidate = _select_candidate(state, candidates)
    if current_candidate is not None:
        if current_candidate.get("ambiguous"):
            _add_concern(
                concerns,
                "candidate-projection-ambiguous",
                "Текущий candidate выведен из legacy producer attempt/top-level records без однозначного ticket.current_candidate pointer.",
            )
    elif any(ticket.get("current_candidate") for ticket in state.get("tickets", [])):
        _add_concern(
            concerns,
            "candidate-pointer-unresolved",
            "ticket.current_candidate задан, но соответствующая canonical candidate record отсутствует; попытки не используются для подмены pointer.",
        )
    elif phase in {"EXECUTE", "VERIFY", "ACCEPT"}:
        _add_concern(concerns, "candidate-missing", "Для текущей фазы в ledger не записан candidate SHA/tree SHA.")

    blockers = [
        {
            "id": issue.get("id"),
            "type": issue.get("type"),
            "cause": issue.get("cause"),
            "disposition": issue.get("disposition"),
            "affected_refs": issue.get("affected_refs", []),
        }
        for issue in state.get("issues", [])
        if issue.get("impact") == "blocking" and not issue.get("invalidated_by")
    ]
    if control == "BLOCKED" and not blockers:
        _add_concern(
            concerns,
            "blocked-without-issue",
            "lifecycle.control=BLOCKED, но в ledger нет issue с impact=blocking; показан lifecycle reason.",
        )
        blockers.append(
            {
                "id": "lifecycle",
                "type": "lifecycle",
                "cause": None,
                "disposition": lifecycle.get("reason") or "BLOCKED",
                "affected_refs": [],
            }
        )

    next_action = lifecycle.get("next_action")
    if not isinstance(next_action, dict):
        _add_concern(concerns, "next-action-missing", "В ledger отсутствует lifecycle.next_action.")
        next_action = {"kind": None, "subject_refs": [], "preconditions": [], "read_refs": []}

    reason = lifecycle.get("reason")
    settings = resolved_run_settings(state)
    last_action = {
        "recorded_reason": reason,
        "revision": state.get("revision"),
        "updated_at": state.get("updated_at"),
        "note": "Ledger хранит revision/updated_at, но не append-only историю действий.",
    }
    _add_concern(
        concerns,
        "action-history",
        "Точный last action не записан в ledger; показаны последняя publication revision/time и lifecycle reason.",
    )

    if phase is None or control is None:
        _add_concern(concerns, "lifecycle-missing", "В ledger не хватает phase/control для общего статуса run.")

    return {
        "source": {
            "ledger_path": str(ledger_path),
            "sha256": sha256_bytes(raw),
            "loaded_at": _now(),
        },
        "run": {
            "id": state.get("run_id"),
            "revision": state.get("revision"),
            "updated_at": state.get("updated_at"),
            "phase": phase,
            "control": control,
            "reason": reason,
            "owner_epoch": state.get("owner", {}).get("epoch"),
            "run_settings": settings,
            "preset_display": run_settings_display(settings),
        },
        "run_settings": settings,
        "gates": gates,
        "tickets": tickets,
        "design_publication": design_publication,
        "design_publication_history": design_publication_history,
        "design_review_attempts": design_review_attempts,
        "ticket_counts": {
            status: sum(1 for ticket in tickets if ticket.get("status") == status)
            for status in sorted({ticket.get("status") for ticket in tickets})
            if status is not None
        },
        "active": active,
        "blockers": blockers,
        "findings": [
            {**item, "current": not bool(item.get("invalidated_by"))}
            for item in state.get("findings", [])
        ],
        "requirements_publications": state.get("requirements_publications", []),
        "version_provenance": state.get("runtime_provenance", {
            "creation_skill_version": state.get("skill_version"),
            "last_mutating_skill_version": state.get("skill_version"),
            "current_schema_version": state.get("schema_version"),
            "applied_migrations": [],
        }),
        "adjudications": [item for item in state.get("decisions", []) if item.get("type") == "reviewer_adjudication"],
        "usage": state.get("usage", {"tokens": None, "token_reason": "token meter unavailable", "counters": {}, "shared_setup": {}, "gate_costs": {}, "trace": []}),
        "candidate": {"current": current_candidate, "all": candidates},
        "last_action": last_action,
        "next_action": next_action,
        "overall": {"control": control, "reason": reason, "terminal": control in TERMINAL_CONTROLS},
        "concerns": concerns,
    }


def _resolve_ledger(control_root: Path, run_id: str | None) -> tuple[str, Path]:
    root = control_root.expanduser().resolve()
    if run_id:
        selected = paths(root, run_id)["ledger"]
        runs_root = (root / ".autopilot" / "runs").resolve()
        try:
            relative = selected.resolve().relative_to(runs_root)
        except ValueError as exc:
            raise LedgerError("run ledger must remain under the canonical .autopilot/runs root") from exc
        if relative.parts != (Path(run_id).name, "ledger.json"):
            raise LedgerError("run_id must resolve to one canonical .autopilot/runs/<run-id>/ledger.json")
        return run_id, selected

    base = root / ".autopilot"
    if base.is_symlink():
        raise LedgerError("canonical .autopilot namespace may not be a symlink")
    candidates = sorted(path for path in (base / "runs").glob("*/ledger.json") if path.is_file() and not path.is_symlink())
    if not candidates:
        raise LedgerError(f"no current ledger found under {base / 'runs'}")
    if len(candidates) > 1:
        names = ", ".join(path.parent.name for path in candidates)
        raise LedgerError(f"multiple ledgers found ({names}); pass --run-id explicitly")
    return candidates[0].parent.name, candidates[0]


def load_projection(control_root: Path, run_id: str | None) -> dict[str, Any]:
    selected_run, ledger_path = _resolve_ledger(control_root, run_id)
    expected = paths(control_root, selected_run)["ledger"]
    if ledger_path != expected:
        raise LedgerError("resolved ledger is not the canonical run ledger")
    state, raw = load_state({"ledger": ledger_path})
    return project_ledger(state, ledger_path, raw)


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "CodexAutopilotDashboard/1.0"

    @property
    def dashboard_server(self) -> "DashboardServer":
        return self.server  # type: ignore[return-value]

    def _send_bytes(self, status: int, data: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, status: int, value: Any) -> None:
        self._send_bytes(
            status,
            (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            try:
                self._send_bytes(HTTPStatus.OK, HTML_PATH.read_bytes(), "text/html; charset=utf-8")
            except OSError as exc:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(exc)})
            return

        if parsed.path == "/api/ledger":
            requested_run = parse_qs(parsed.query).get("run_id", [self.dashboard_server.run_id])[0]
            try:
                projection = load_projection(self.dashboard_server.control_root, requested_run or None)
            except (LedgerError, OSError, ValueError, KeyError) as exc:
                self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"ok": False, "error": str(exc), "read_only": True})
                return
            self._send_json(HTTPStatus.OK, {"ok": True, "read_only": True, "data": projection})
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802 - explicit read-only guard
        self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "error": "dashboard is read-only"})

    do_PUT = do_POST
    do_PATCH = do_POST
    do_DELETE = do_POST

    def log_message(self, format: str, *args: Any) -> None:
        # Keep the local terminal useful: only errors are printed by the
        # default server loop, while every response remains read-only.
        if args and str(args[1]).startswith("4"):
            super().log_message(format, *args)


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], control_root: Path, run_id: str | None):
        super().__init__(address, DashboardHandler)
        self.control_root = control_root
        self.run_id = run_id


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve a read-only Codex Autopilot ledger dashboard")
    parser.add_argument("--control-root", default=".", help="repository/control root containing .autopilot")
    parser.add_argument("--run-id", help="run directory under .autopilot/runs; optional when exactly one exists")
    parser.add_argument("--host", default="127.0.0.1", help="bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="bind port (default: 8765; 0 chooses a free port)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    control_root = Path(args.control_root).expanduser().resolve()
    try:
        selected_run, _ = _resolve_ledger(control_root, args.run_id)
        server = DashboardServer((args.host, args.port), control_root, selected_run)
    except (LedgerError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2

    address = server.server_address
    print(f"Read-only dashboard: http://{address[0]}:{address[1]}/?run_id={selected_run}", flush=True)
    print(f"Source: {control_root / '.autopilot' / 'runs' / selected_run / 'ledger.json'}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
