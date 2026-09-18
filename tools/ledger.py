#!/usr/bin/env python3
"""Deterministic Codex Autopilot ledger and contract helper.

The helper owns no orchestration loop and never invokes a model.  It validates
closed-schema payloads, publishes one ledger revision under an advisory lock,
and records exact evidence bytes.  Git mutations remain native approved
orchestrator actions; this module only validates their receipts.
"""

from __future__ import annotations

import argparse
import copy
import contextvars
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

SKILL_VERSION = "1.1.0"
POLICY_VERSION = "v1-manual-g5"
SCHEMA_VERSION = "1.0"
STATE_CONTRACT_VERSION = "1.1"
WRITER_VERSION = SKILL_VERSION
COMPATIBILITY_FLOOR = "1.0.0"
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
SEMVER_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
PHASES = ("PREFLIGHT", "INTENT", "DESIGN", "PLAN", "EXECUTE", "VERIFY", "ACCEPT")
CONTROLS = ("ACTIVE", "QUIESCING", "PAUSED", "BLOCKED", "RECOVERING", "ACCEPTED", "FAILED", "CANCELLED")
CAUSES = ("implementation", "contract", "oracle", "environment", "permission", "ownership", "orchestration", "user_intent", "unknown")
VALID_CONTEXT_GRADES = {"PACKET_SCOPED", "DEGRADED_CONTEXT", "MANUAL_ATTESTED_CLEAN", "STRICT_FRESH"}
DEFAULT_RUN_SETTINGS = {"interaction_mode": "semi", "depth": "normal"}
EVENT_CONTROL_TABLE = {
    "ACTIVE": frozenset({
        "worker.dispatch", "review.dispatch", "run.recover", "lifecycle.advance", "run.cancel.request",
        "attempt.ingest", "attempt.reconcile", "candidate.publish", "review.integrate",
        "repair.authorize", "review.adjudicate", "effect.prepare", "effect.reconcile",
        "handoff.prepare", "acceptance.import", "intent.amend", "usage.publish",
        "ticket.ready", "intent.publish", "requirements.adopt", "design.publish", "review.currentness.migrate",
    }),
    "BLOCKED": frozenset({
        "worker.dispatch", "review.dispatch", "run.recover", "lifecycle.advance", "run.cancel.request",
        "attempt.ingest", "attempt.reconcile", "candidate.publish",
        "repair.authorize", "review.adjudicate", "effect.prepare", "effect.reconcile",
        "handoff.prepare", "acceptance.import", "intent.amend", "usage.publish",
        "intent.publish", "requirements.adopt", "design.publish", "review.currentness.migrate",
    }),
    "QUIESCING": frozenset({"lifecycle.advance", "run.cancel.finalize", "attempt.ingest", "attempt.reconcile", "effect.reconcile", "usage.publish"}),
    "PAUSED": frozenset({"run.resume", "run.recover", "attempt.ingest", "attempt.reconcile", "effect.reconcile", "intent.amend", "usage.publish"}),
    "RECOVERING": frozenset({"lifecycle.advance", "run.cancel.request", "attempt.ingest", "attempt.reconcile", "effect.reconcile", "intent.publish", "usage.publish"}),
    "ACCEPTED": frozenset(),
    "FAILED": frozenset(),
    "CANCELLED": frozenset(),
}
EVENT_PHASE_TABLE = {
    "worker.dispatch": frozenset({"EXECUTE"}),
    "review.dispatch": frozenset({"DESIGN", "PLAN", "EXECUTE", "VERIFY", "ACCEPT"}),
    "run.recover": frozenset(PHASES),
    "lifecycle.advance": frozenset(PHASES),
    "run.cancel.request": frozenset(PHASES),
    "run.cancel.finalize": frozenset(PHASES),
    "run.resume": frozenset(PHASES),
    "attempt.ingest": frozenset(PHASES),
    "attempt.reconcile": frozenset(PHASES),
    "candidate.publish": frozenset({"EXECUTE"}),
    "review.integrate": frozenset({"EXECUTE"}),
    "repair.authorize": frozenset({"EXECUTE"}),
    "review.adjudicate": frozenset({"DESIGN", "PLAN", "EXECUTE", "VERIFY", "ACCEPT"}),
    "effect.prepare": frozenset(PHASES),
    "effect.reconcile": frozenset(PHASES),
    "handoff.prepare": frozenset({"EXECUTE", "VERIFY", "ACCEPT"}),
    "acceptance.import": frozenset({"VERIFY", "ACCEPT"}),
    "intent.amend": frozenset(PHASES),
    "usage.publish": frozenset(PHASES),
    "ticket.ready": frozenset({"EXECUTE"}),
    "intent.publish": frozenset({"PREFLIGHT", "INTENT"}),
    "requirements.adopt": frozenset({"DESIGN"}),
    "design.publish": frozenset({"DESIGN"}),
    "review.currentness.migrate": frozenset({"DESIGN", "PLAN"}),
}
PHASE_TRANSITION_TABLE = {
    phase: frozenset({phase, *([PHASES[index + 1]] if index + 1 < len(PHASES) else [])})
    for index, phase in enumerate(PHASES)
}
CONTROL_TRANSITION_TABLE = {
    "ACTIVE": frozenset({"ACTIVE", "BLOCKED", "QUIESCING", "FAILED", "ACCEPTED"}),
    "BLOCKED": frozenset({"ACTIVE", "BLOCKED", "QUIESCING", "RECOVERING", "FAILED"}),
    "QUIESCING": frozenset({"QUIESCING", "PAUSED", "FAILED"}),
    "PAUSED": frozenset({"PAUSED", "ACTIVE", "RECOVERING", "QUIESCING"}),
    "RECOVERING": frozenset({"RECOVERING", "ACTIVE", "BLOCKED", "QUIESCING", "PAUSED"}),
    "ACCEPTED": frozenset({"ACCEPTED"}),
    "FAILED": frozenset({"FAILED"}),
    "CANCELLED": frozenset({"CANCELLED"}),
}
TERMINAL_ATTEMPT_STATES = frozenset({"RETURNED", "LOST", "INTERRUPTED"})
TERMINAL_CONTROLS = frozenset({"ACCEPTED", "FAILED", "CANCELLED"})
EFFECT_TRANSITIONS = {
    "prepared": frozenset({"applied", "uncertain", "abandoned"}),
    "uncertain": frozenset({"applied", "abandoned"}),
    "applied": frozenset({"finalized"}),
    "abandoned": frozenset(),
    "finalized": frozenset(),
}
RUN_SETTING_LABELS = {
    "interaction_mode": {"semi": "полуавтомат", "full": "полный автомат"},
    "depth": {"normal": "обычная", "deep": "глубокая"},
}
USAGE_FIELDS = (
    "helper_calls", "model_turns", "orchestrator_turns", "attempt_registrations", "spawn_calls", "wait_calls", "git_calls",
    "internal_publications", "packet_bytes", "return_bytes", "brief_bytes", "wall_time_ms",
    "approvals", "user_interventions", "manual_handoffs", "manual_setup", "manual_wait",
)


class LedgerError(Exception):
    """A safe, user-actionable validation or publication failure."""


class IdempotentResult(Exception):
    """Abort a locked transaction without publication and return prior success."""

    def __init__(self, result: dict[str, Any]):
        super().__init__("idempotent")
        self.result = result


@dataclass(frozen=True)
class PlannedWrite:
    """One immutable destination and its exact intended bytes."""

    destination: Path
    data: bytes
    kind: str


@dataclass(frozen=True)
class ImmutableWritePlan:
    """Preflighted immutable writes published only after transition validation."""

    writes: tuple[PlannedWrite, ...]

    def preflight(self) -> None:
        seen: dict[Path, bytes] = {}
        for write in self.writes:
            destination = write.destination
            prior = seen.get(destination)
            if prior is not None and prior != write.data:
                fail(f"immutable write plan has conflicting bytes for {destination}")
            seen[destination] = write.data
            if destination.parent.exists():
                if destination.parent.is_symlink() or not destination.parent.is_dir():
                    fail(f"immutable write namespace is not a regular directory: {destination.parent}")
            if destination.exists() or destination.is_symlink():
                regular_non_symlink(destination)
                if destination.read_bytes() != write.data:
                    fail(f"immutable destination already exists with different bytes: {destination}")

    def publish(self) -> tuple[PlannedWrite, ...]:
        self.preflight()
        created: list[PlannedWrite] = []
        for write in self.writes:
            if atomic_create(write.destination, write.data):
                created.append(write)
        return tuple(created)


class WritePlanBuilder:
    """Collect writes while a locked transition is being evaluated."""

    def __init__(self) -> None:
        self._writes: dict[Path, PlannedWrite] = {}

    def add(self, destination: Path, data: bytes, kind: str) -> None:
        destination = Path(destination)
        planned = PlannedWrite(destination, bytes(data), kind)
        prior = self._writes.get(destination)
        if prior is not None and prior.data != planned.data:
            fail(f"immutable write plan has conflicting bytes for {destination}")
        self._writes[destination] = planned

    def freeze(self) -> ImmutableWritePlan:
        return ImmutableWritePlan(tuple(self._writes.values()))


_ACTIVE_WRITE_PLAN: contextvars.ContextVar[WritePlanBuilder | None] = contextvars.ContextVar(
    "autopilot_active_write_plan", default=None
)


def fail(message: str) -> None:
    raise LedgerError(message)


def transition_effect(operation: dict[str, Any], target: str) -> None:
    """Apply the typed durable effect transition table."""
    current = operation.get("state")
    if target not in EFFECT_TRANSITIONS.get(current, frozenset()):
        fail(f"illegal effect transition for {operation.get('id')}: {current} -> {target}")
    operation["state"] = target


def effect_is_unresolved(operation: dict[str, Any]) -> bool:
    """Return whether an operation still needs execution, resolution, or adoption."""
    return operation.get("state") in ("prepared", "uncertain", "applied")


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def zero_usage() -> dict[str, int]:
    return {field: 0 for field in USAGE_FIELDS}


def allowed_events(state: dict[str, Any]) -> list[str]:
    """Return the canonical event IDs admitted by the current phase/control."""
    lifecycle = state.get("lifecycle", {})
    control = lifecycle.get("control")
    phase = lifecycle.get("phase")
    events = set(EVENT_CONTROL_TABLE.get(control, ()))
    events = {event_id for event_id in events if phase in EVENT_PHASE_TABLE.get(event_id, frozenset())}
    if control != "QUIESCING":
        events.discard("run.cancel.finalize")
    if control != "PAUSED":
        events.discard("run.resume")
    if control == "BLOCKED" and _blocked_repair_review_integrate_ready(state):
        events.add("review.integrate")
    return sorted(events)


def admit_event(state: dict[str, Any], event_id: str) -> None:
    """Fail closed when a typed lifecycle event is not in the shared admission projection."""
    lifecycle = state.get("lifecycle", {})
    phase = lifecycle.get("phase")
    required_phases = EVENT_PHASE_TABLE.get(event_id, frozenset())
    if phase not in required_phases:
        fail(
            f"event {event_id!r} requires phase {'/'.join(sorted(required_phases))}; "
            f"current phase/control is {phase} × {lifecycle.get('control')}"
        )
    if event_id not in allowed_events(state):
        fail(
            f"event {event_id!r} is not admitted in "
            f"{phase} × {lifecycle.get('control')}"
        )


def validate_control_transition(current: str, target: str) -> None:
    """Validate control changes against the shared transition table."""
    if target not in CONTROL_TRANSITION_TABLE.get(current, frozenset()):
        fail(f"illegal control transition: {current} -> {target}")


def _action_event_id(kind: Any) -> str | None:
    if not isinstance(kind, str):
        return None
    if kind.startswith("await_"):
        return "attempt.ingest"
    if kind in {"prepare_g2_coverage_review", "prepare_g3_plan_review", "review_change"}:
        return "review.dispatch" if kind.startswith("prepare_") or kind == "review_change" else None
    if kind in {
        "dispatch_ticket", "dispatch_repair", "dispatch_repair_with_blocker_retained",
        "prepare_g2_coverage_review", "prepare_g3_plan_review",
    }:
        return "worker.dispatch"
    if kind == "recover_attempt":
        return "run.recover"
    if kind in {"reconcile_actual_state", "reconcile_terminal_attempts"}:
        return "attempt.reconcile"
    if kind in {"audit_worker_return_and_prepare_candidate", "preserve_blocked_candidate", "adopt_applied_effect"}:
        return "candidate.publish"
    if kind in {"authorize_repair", "authorize_grouped_repair", "resolve_blocker_or_authorize_candidate_bound_repair"}:
        return "repair.authorize"
    if kind in {"adjudicate_review_disagreement"}:
        return "review.adjudicate"
    if kind in {"integrate_candidate", "integrate_reviewed_repair"}:
        return "review.integrate"
    if kind in {"review_candidate", "review_change"}:
        return "review.dispatch"
    if kind == "import_manual_review":
        return "acceptance.import"
    if kind == "prepare_acceptance_handoff":
        return "handoff.prepare"
    if kind == "mark_ticket_ready":
        return "ticket.ready"
    if kind == "publish_design_bundle":
        return "design.publish"
    if kind in {"apply_prepared_effect"}:
        return "effect.prepare"
    if kind in {"reconcile_effect", "reconcile_uncertain_effect"}:
        return "effect.reconcile"
    if kind == "resume_run":
        return "run.resume"
    if kind in {"advance_to_intent", "complete_g1", "advance_to_execute", "finalize_acceptance"}:
        return "lifecycle.advance"
    if kind == "stop_reconcile_then_cancel":
        return "run.cancel.request"
    return None


def _review05_grouped_repair_action(state: dict[str, Any]) -> dict[str, Any] | None:
    """Prioritize the exact reconciled Review05 group while retaining old obligations."""
    if state.get("lifecycle", {}).get("control") != "BLOCKED":
        return None
    if any(item.get("state") in ("PREPARED", "DISPATCHED") for item in state.get("attempts", [])):
        return None
    finding_refs = {
        binding.get("finding_ref")
        for event in state.get("finding_binding_reconciliations", [])
        if event.get("review_attempt_ref") == "T02-R17-REVIEW-CODE-05"
        and event.get("ticket_ref") == "T02-R17"
        and event.get("candidate_ref") == "candidate-T02-R17-WORKER-05"
        for binding in event.get("finding_bindings", [])
    }
    projection = finding_obligation_projection(state)
    current = {
        item.get("finding_ref") for item in projection["items"]
        if item.get("status") == "current" and item.get("repairable")
    }
    if len(finding_refs) != 3 or current != finding_refs:
        return None
    candidate = next((item for item in state.get("candidates", []) if item.get("id") == "candidate-T02-R17-WORKER-05"), None)
    blocker_ref = "issue-62c0073109c9529a"
    blocker = next((item for item in state.get("issues", []) if item.get("id") == blocker_ref), None)
    if (
        candidate is None or candidate.get("quality") != "CONTINUATION"
        or blocker is None or blocker.get("impact") != "blocking" or blocker.get("invalidated_by")
        or blocker_ref not in candidate.get("blocker_refs", [])
    ):
        return None
    return {
        "kind": "authorize_grouped_repair",
        "subject_refs": ["T02-R17", candidate["id"], "T02-R17-REVIEW-CODE-05", *sorted(finding_refs)],
        "preconditions": [
            "authorize one bounded repair plan for exactly these three current Review05 findings",
            "retain seven historical T02 carry-forward obligations and the external continuation blocker",
            "reconcile any previously applied external effect before dispatching a repair worker",
        ],
        "read_refs": ["phases/execute.md", "references/routing.md", "references/ledger.md"],
    }


def derive_next_action(state: dict[str, Any]) -> dict[str, Any]:
    """Derive a safe typed disposition from control, attempts, obligations, and candidate pointers."""
    lifecycle = state.get("lifecycle", {})
    stored = lifecycle.get("next_action", {})
    if not isinstance(stored, dict):
        stored = {}
    phase_b = state.get("candidate_model_version") == "1.1"
    action = {
        "kind": stored.get("kind", "inspect_state") if not phase_b else "inspect_state",
        "subject_refs": list(stored.get("subject_refs", [])) if not phase_b else [],
        "preconditions": list(stored.get("preconditions", [])) if not phase_b else [],
        "read_refs": list(stored.get("read_refs", [])) if not phase_b else [],
    }
    attempts = [item for item in state.get("attempts", []) if isinstance(item, dict)]
    attempt_by_id = {item.get("id"): item for item in attempts if item.get("id")}
    refs = action["subject_refs"]
    targets = [attempt_by_id[ref] for ref in refs if ref in attempt_by_id]
    control = lifecycle.get("control")

    if control in TERMINAL_CONTROLS:
        action = {
            "kind": f"terminal_{str(control).lower()}",
            "subject_refs": [], "preconditions": [], "read_refs": ["references/ledger.md"],
            "human_input_required": False,
        }
    elif phase_b:
        user_assisted = [item for item in attempts if item.get("mode") == "user_assisted" and item.get("state") == "PREPARED"]
        active = [item for item in attempts if item.get("mode") != "user_assisted" and item.get("state") in ("PREPARED", "DISPATCHED")]
        stranded = [
            item for item in attempts
            if item.get("state") in ("LOST", "INTERRUPTED")
            and item.get("lease", {}).get("state") in ("active", "quarantined")
        ]
        pending_operations = [item for item in state.get("operations", []) if effect_is_unresolved(item)]
        if (review05_group := _review05_grouped_repair_action(state)) is not None:
            action = review05_group
        elif pending_operations:
            operation = pending_operations[0]
            operation_id = operation.get("id")
            if operation.get("state") == "prepared":
                action = {
                    "kind": "apply_prepared_effect", "subject_refs": [operation_id],
                    "preconditions": ["apply this exact prepared effect once", "record an exact immutable receipt or reconcile its observed state"],
                    "read_refs": ["references/ledger.md", "references/safety.md"],
                }
            elif operation.get("state") == "uncertain":
                action = {
                    "kind": "reconcile_uncertain_effect", "subject_refs": [operation_id],
                    "preconditions": ["inspect the exact target", "record fresh owner resolution evidence", "do not repeat the effect"],
                    "read_refs": ["phases/recover.md", "references/safety.md"],
                }
            elif operation.get("state") == "applied":
                producer = next((item for item in attempts if item.get("id") and item.get("id") == operation.get("attempt_ref")), None)
                if producer is None:
                    producer = next((item for item in attempts if item.get("kind") == "worker" and item.get("candidate_sha") in (None, operation.get("intended_after")) and item.get("checkout") and Path(item["checkout"]).expanduser().resolve() == Path(operation.get("target", "")).expanduser().resolve()), None)
                if operation.get("kind") == "candidate_commit":
                    action = {
                        "kind": "adopt_applied_effect", "subject_refs": [operation_id, *([producer["id"]] if producer else [])],
                        "preconditions": ["verify the immutable effect receipt and exact Git target", "finalize candidate linkage without repeating Git"],
                        "read_refs": ["phases/recover.md", "references/ledger.md"],
                    }
                else:
                    action = {
                        "kind": "resume_after_effect_reconciliation", "subject_refs": [operation_id],
                        "preconditions": ["re-read current ledger", "verify the resulting subject before further work"],
                        "read_refs": ["phases/recover.md", "references/ledger.md"],
                    }
        # Only an actual in-flight attempt creates a wait. A cached await or terminal
        # attempt is not executable orchestration authority.
        elif active:
            if control in ("QUIESCING", "PAUSED", "RECOVERING"):
                safe_active = [item for item in active if item.get("state") in ("PREPARED", "DISPATCHED")]
                if safe_active:
                    active = safe_active
            if len(active) == 1:
                attempt = active[0]
                kind = "await_review_return" if attempt.get("kind") == "review" else "await_worker_return"
                action = {
                    "kind": kind, "subject_refs": [attempt["id"]],
                    "preconditions": ["internal orchestration wait; not a user checkpoint", "attempt remains nonterminal; ingest its exact return"],
                    "read_refs": ["phases/execute.md", "phases/recover.md"],
                }
            else:
                action = {
                    "kind": "human_input_required",
                    "subject_refs": [item.get("id") for item in active if item.get("id")],
                    "preconditions": ["multiple nonterminal attempts require owner reconciliation before choosing a next action"],
                    "read_refs": ["phases/recover.md", "references/ledger.md"],
                    "human_input_required": True,
                }
        elif stranded and control in ("ACTIVE", "BLOCKED", "PAUSED") and lifecycle.get("reason") != "attempt_finalization_quarantined":
            action = {
                "kind": "recover_attempt",
                "subject_refs": [item["id"] for item in stranded if item.get("id")],
                "preconditions": ["reconcile the exact lost/interrupted attempts and their active or quarantined leases before repair authorization or dispatch"],
                "read_refs": ["phases/recover.md", "references/ledger.md"],
            }
        elif stranded and control in ("QUIESCING", "RECOVERING"):
            action = {
                "kind": "reconcile_actual_state",
                "subject_refs": [item["id"] for item in stranded if item.get("id")],
                "preconditions": ["reconcile the exact lost/interrupted attempts and their active or quarantined leases before further work"],
                "read_refs": ["phases/recover.md", "references/ledger.md"],
            }
        elif user_assisted and control == "BLOCKED":
            action = {
                "kind": "import_manual_review", "subject_refs": [item["id"] for item in user_assisted],
                "preconditions": ["exact external return, clean environment/context receipts, and unchanged integrity baseline"],
                "read_refs": ["phases/accept.md", "references/safety.md"],
            }
        elif control == "BLOCKED" and lifecycle.get("reason") == "attempt_finalized_no_candidate":
            finalized = [
                item for item in attempts
                if item.get("finalization_ref") and item.get("subject_ref") in {ticket.get("id") for ticket in state.get("tickets", [])}
            ]
            latest = finalized[-1] if finalized else None
            action = {
                "kind": "retry_changed_attempt",
                "subject_refs": [latest.get("subject_ref"), latest.get("id")] if latest else [],
                "preconditions": ["use the verified baseline", "change the attempt plan or repair contract before retry", "use a fresh attempt ID"],
                "read_refs": ["phases/execute.md", "references/routing.md", "references/ledger.md"],
            }
        elif control == "BLOCKED" and lifecycle.get("reason") == "attempt_finalization_quarantined":
            finalized = [item for item in attempts if item.get("finalization_ref") and item.get("lease", {}).get("state") == "quarantined"]
            latest = finalized[-1] if finalized else None
            action = {
                "kind": "recover_attempt",
                "subject_refs": [latest.get("id")] if latest else [],
                "preconditions": ["inspect the exact foreign or uncertain checkout write-set", "reconcile the quarantined lease only after writer stop and checkout ownership are proven"],
                "read_refs": ["phases/recover.md", "references/ledger.md", "references/safety.md"],
            }
        elif control == "BLOCKED" and (blocked_repair_action := _blocked_repair_candidate_action(state)) is not None:
            action = blocked_repair_action
        elif control == "BLOCKED":
            projection = finding_obligation_projection(state)
            open_obligations = [item for item in projection["obligations"] if item.get("status") != "closed"]
            active_blockers = [item for item in state.get("issues", []) if item.get("impact") == "blocking" and not item.get("invalidated_by")]
            repairable = [
                item for item in projection["items"]
                if item.get("repairable") and any(
                    obligation.get("finding_ref") == item.get("finding_ref")
                    and obligation.get("status") != "closed" for obligation in open_obligations
                )
            ]
            grouped_repair = None
            if len(repairable) >= 2:
                ticket_sets = [item.get("unresolved_ticket_refs", item.get("affected_ticket_refs", [])) for item in repairable]
                candidate_refs = {item.get("source_candidate_ref") for item in repairable}
                finding_records = {
                    item.get("id"): item for item in state.get("findings", [])
                }
                source_refs = {
                    finding_records.get(item.get("finding_ref"), {}).get("source_ref")
                    for item in repairable
                }
                if (
                    all(len(refs) == 1 for refs in ticket_sets)
                    and len({refs[0] for refs in ticket_sets}) == 1
                    and len(candidate_refs) == 1 and None not in candidate_refs
                    and len(source_refs) == 1 and None not in source_refs
                    and len(repairable) == 3
                ):
                    source_ref = next(iter(source_refs))
                    source_attempt = attempt_by_id.get(source_ref)
                    candidate_ref = next(iter(candidate_refs))
                    ticket_ref = ticket_sets[0][0]
                    ticket_record = next((item for item in state.get("tickets", []) if item.get("id") == ticket_ref), None)
                    current_candidate = current_candidate_record(state, ticket_record) if ticket_record else None
                    if (
                        source_attempt and source_attempt.get("kind") == "review"
                        and source_attempt.get("subject_ref") == ticket_ref
                        and current_candidate is not None
                        and source_attempt.get("candidate_sha") == current_candidate.get("sha")
                        and candidate_ref == current_candidate.get("id")
                    ):
                        grouped_refs = sorted(item["finding_ref"] for item in repairable)
                        grouped_repair = {
                            "kind": "authorize_grouped_repair",
                            "subject_refs": [ticket_ref, candidate_ref, source_ref, *grouped_refs],
                            "preconditions": [
                                "authorize one bounded repair plan for exactly these three current findings on the same ticket and continuation candidate",
                                "retain historical carry-forward obligations and the external continuation blocker",
                            ],
                            "read_refs": ["phases/execute.md", "references/routing.md", "references/ledger.md"],
                        }
            if grouped_repair is not None:
                action = grouped_repair
            elif len(repairable) == 1 and all(
                item.get("status") == "open" and item.get("applicability") == "current"
                for item in open_obligations
            ):
                finding_ref = repairable[0]["finding_ref"]
                ticket_refs = repairable[0].get("unresolved_ticket_refs", repairable[0].get("affected_ticket_refs", []))
                action = {
                    "kind": "authorize_repair",
                    "subject_refs": [*ticket_refs, finding_ref],
                    "preconditions": ["authorize only this current ticket-scoped finding with a bounded repair contract"],
                    "read_refs": ["phases/execute.md", "references/routing.md"],
                }
            elif not open_obligations and len(active_blockers) == 1 and any(
                item.get("issue_ref") == active_blockers[0].get("id") and item.get("repairable")
                for item in projection["mirrored_issues"]
            ):
                blocker = active_blockers[0]
                ticket_refs = sorted(ref for ref in blocker.get("affected_refs", []) if ref in {item.get("id") for item in state.get("tickets", [])})
                if len(ticket_refs) == 1:
                    action = {
                        "kind": "authorize_repair", "subject_refs": [ticket_refs[0], blocker["id"]],
                        "preconditions": ["authorize only this current ticket-scoped blocking issue with a bounded repair contract"],
                        "read_refs": ["phases/execute.md", "references/routing.md"],
                    }
                else:
                    action = {
                        "kind": "human_input_required", "subject_refs": [blocker["id"]],
                        "preconditions": ["blocking issue must be bound to exactly one ticket before repair authorization"],
                        "read_refs": ["references/routing.md", "references/ledger.md"],
                        "human_input_required": True,
                    }
            elif open_obligations or active_blockers:
                action = {
                    "kind": "human_input_required", "subject_refs": [
                        ref for item in open_obligations
                        for ref in ([item.get("finding_ref")] + item.get("issue_refs", [])) if ref
                    ],
                    "preconditions": ["resolve or explicitly bind every current blocking obligation before resuming"],
                    "read_refs": ["phases/execute.md", "references/routing.md"],
                    "human_input_required": True,
                }
            else:
                action = {
                    "kind": "human_input_required", "subject_refs": [],
                    "preconditions": ["BLOCKED state has no verified repairable finding; owner disposition is required"],
                    "read_refs": ["references/routing.md", "references/ledger.md"],
                    "human_input_required": True,
                }
        elif control in ("QUIESCING", "PAUSED", "RECOVERING"):
            if control == "PAUSED":
                action = {
                    "kind": "resume_run", "subject_refs": [],
                    "preconditions": ["resume only after safe reconciliation is complete"],
                    "read_refs": ["phases/recover.md", "references/ledger.md"],
                }
            elif control == "RECOVERING":
                action = {
                    "kind": "reconcile_actual_state", "subject_refs": [],
                    "preconditions": ["reconcile effects and stale writer state before ordinary dispatch"],
                    "read_refs": ["phases/recover.md", "references/ledger.md"],
                }
            else:
                action = {
                    "kind": "human_input_required", "subject_refs": [],
                    "preconditions": ["complete stop evidence and choose safe pause or cancellation finalization"],
                    "read_refs": ["phases/recover.md", "references/ledger.md"],
                    "human_input_required": True,
                }
        else:
            projection = finding_obligation_projection(state)
            open_obligations = [item for item in projection["obligations"] if item.get("status") != "closed"]
            repairable = [
                item for item in projection["items"]
                if item.get("repairable") and any(
                    obligation.get("finding_ref") == item.get("finding_ref")
                    and obligation.get("status") == "open" and obligation.get("applicability") == "current"
                    for obligation in open_obligations
                )
            ]
            if open_obligations:
                if len(repairable) == 1 and all(
                    item.get("status") == "open" and item.get("applicability") == "current"
                    for item in open_obligations
                ):
                    finding_ref = repairable[0]["finding_ref"]
                    action = {
                        "kind": "authorize_repair",
                        "subject_refs": [*repairable[0].get("unresolved_ticket_refs", repairable[0].get("affected_ticket_refs", [])), finding_ref],
                        "preconditions": ["authorize only this current ticket-scoped finding with a bounded repair contract"],
                        "read_refs": ["phases/execute.md", "references/routing.md"],
                    }
                else:
                    action = {
                        "kind": "human_input_required", "subject_refs": [
                            ref for item in open_obligations
                            for ref in ([item.get("finding_ref")] + item.get("issue_refs", [])) if ref
                        ],
                        "preconditions": ["resolve or explicitly bind every blocking obligation before integration or lifecycle advancement"],
                        "read_refs": ["phases/execute.md", "references/routing.md"],
                        "human_input_required": True,
                    }
            elif any(item.get("impact") == "blocking" and not item.get("invalidated_by") for item in state.get("issues", [])):
                action = {
                    "kind": "human_input_required", "subject_refs": [
                        item["id"] for item in state.get("issues", [])
                        if item.get("impact") == "blocking" and not item.get("invalidated_by")
                    ],
                    "preconditions": ["inspect and disposition every active blocking issue before advancing"],
                    "read_refs": ["references/routing.md", "references/ledger.md"],
                    "human_input_required": True,
                }
            else:
                candidate_preparations = []
                for ticket in state.get("tickets", []):
                    attempt_ref = ticket.get("last_worker_attempt")
                    attempt = attempt_by_id.get(attempt_ref)
                    if (
                        attempt is not None
                        and attempt.get("kind") == "worker"
                        and attempt.get("subject_ref") == ticket.get("id")
                        and attempt.get("state") == "RETURNED"
                        and attempt.get("return_ref")
                        and attempt.get("candidate_sha") is None
                        and attempt.get("candidate_tree_sha") is None
                        and attempt.get("lease", {}).get("state") == "active"
                        and ticket.get("current_attempt") == attempt_ref
                        and ticket.get("current_worker_attempt") is None
                        and ticket.get("state") not in ("CANCELLED", "STALE", "INTEGRATED")
                    ):
                        # A validated non-DONE worker return moves the run to BLOCKED
                        # and creates a durable issue. Under ACTIVE control with no
                        # open blockers, this exact latest return is the only legal
                        # source for starting candidate audit/publication.
                        candidate_preparations.append((ticket, attempt))
                if candidate_preparations:
                    ticket, attempt = candidate_preparations[0]
                    action = {
                        "kind": "audit_worker_return_and_prepare_candidate",
                        "subject_refs": [ticket["id"], attempt["id"]],
                        "preconditions": ["exact latest same-ticket worker return is validated DONE", "audit the actual write set and prepare the candidate effect before publication"],
                        "read_refs": ["phases/execute.md", "references/safety.md"],
                    }
                else:
                    candidates_ready: list[tuple[dict[str, Any], dict[str, Any]]] = []
                    for ticket in state.get("tickets", []):
                        candidate = current_candidate_record(state, ticket)
                        if candidate is not None:
                            candidates_ready.append((ticket, candidate))
                    pending_review = next((pair for pair in candidates_ready if pair[1].get("review_status") != "PASS"), None)
                    pending_integration = next((pair for pair in candidates_ready if pair[1].get("review_status") == "PASS" and pair[1].get("integration_status") != "INTEGRATED"), None)
                    if pending_integration is not None:
                        ticket, candidate = pending_integration
                        if candidate.get("quality") == "CONTINUATION":
                            action = {
                                "kind": "human_input_required", "subject_refs": [ticket["id"], candidate["id"]],
                                "preconditions": ["continuation-only candidates require an authorized repair and fresh review; do not integrate"],
                                "read_refs": ["phases/execute.md", "references/routing.md"],
                                "human_input_required": True,
                            }
                        else:
                            action = {
                                "kind": "integrate_candidate", "subject_refs": [ticket["id"], candidate["id"]],
                                "preconditions": ["accepted PASS review is current and all finding obligations are closed"],
                                "read_refs": ["phases/execute.md", "references/ledger.md"],
                            }
                    elif pending_review is not None:
                        ticket, candidate = pending_review
                        action = {
                            "kind": "review_candidate", "subject_refs": [ticket["id"], candidate["id"]],
                            "preconditions": ["prepare an independent review bound to the explicit current candidate"],
                            "read_refs": ["contracts/reviewer.md", "phases/execute.md"],
                        }
                    elif state.get("lifecycle", {}).get("phase") == "EXECUTE":
                        ready_ticket = next((item for item in state.get("tickets", []) if item.get("state") == "READY" and not item.get("current_candidate")), None)
                        planned_ticket = next((item for item in state.get("tickets", []) if item.get("state") == "PLANNED"), None)
                        if ready_ticket is not None:
                            action = {
                                "kind": "dispatch_ticket", "subject_refs": [ready_ticket["id"]],
                                "preconditions": ["fresh packet, admitted worker.dispatch event, and available lease zone"],
                                "read_refs": ["phases/execute.md", "contracts/worker.md"],
                            }
                        elif planned_ticket is not None:
                            action = {
                                "kind": "mark_ticket_ready", "subject_refs": [planned_ticket["id"]],
                                "preconditions": ["current dependencies, criteria, and contracts are satisfied"],
                                "read_refs": ["phases/execute.md", "references/ledger.md"],
                            }
                        else:
                            action = {
                                "kind": "human_input_required", "subject_refs": [],
                                "preconditions": ["no current executable ticket or candidate disposition is available"],
                                "read_refs": ["phases/execute.md", "references/ledger.md"],
                                "human_input_required": True,
                            }
                    elif state.get("lifecycle", {}).get("phase") == "DESIGN":
                        if not isinstance(state.get("design_publication"), dict) or state.get("design_publication", {}).get("status") != "PUBLISHED":
                            action = {
                                "kind": "publish_design_bundle", "subject_refs": [],
                                "preconditions": ["requirements and design bundle are complete and current"],
                                "read_refs": ["phases/design.md", "references/ledger.md"],
                            }
                        elif not design_review_pass(state, "coverage"):
                            action = {
                                "kind": "prepare_g2_coverage_review", "subject_refs": [state["design_publication"].get("id")],
                                "preconditions": ["independent coverage review of the current design bundle"],
                                "read_refs": ["phases/design.md", "contracts/reviewer.md"],
                            }
                        else:
                            action = {
                                "kind": "prepare_g3_plan_review", "subject_refs": [state["design_publication"].get("id")],
                                "preconditions": ["independent plan review of the current design bundle; G3 advances to PLAN"],
                                "read_refs": ["phases/design.md", "contracts/reviewer.md"],
                            }
                    elif state.get("lifecycle", {}).get("phase") == "PLAN":
                        if design_review_pass(state, "coverage") and design_review_pass(state, "plan"):
                            action = {
                                "kind": "advance_to_execute", "subject_refs": [state.get("design_publication", {}).get("id")],
                                "preconditions": ["current G2 coverage PASS, G3 plan PASS, and every ticket PLANNED/READY"],
                                "read_refs": ["phases/execute.md", "references/ledger.md"],
                            }
                        else:
                            action = {
                                "kind": "human_input_required", "subject_refs": [],
                                "preconditions": ["current G2/G3 evidence is incomplete; inspect design review state"],
                                "read_refs": ["phases/design.md", "references/ledger.md"],
                                "human_input_required": True,
                            }
                    elif state.get("lifecycle", {}).get("phase") == "PREFLIGHT":
                        action = {
                            "kind": "advance_to_intent", "subject_refs": [],
                            "preconditions": ["repository preflight and owner setup are complete"],
                            "read_refs": ["phases/start.md", "references/ledger.md"],
                        }
                    elif state.get("lifecycle", {}).get("phase") == "INTENT":
                        action = {
                            "kind": "complete_g1", "subject_refs": [state.get("intent", {}).get("document_ref")] if state.get("intent", {}).get("document_ref") else [],
                            "preconditions": ["current intent document hash and G1 inputs are verified"],
                            "read_refs": ["phases/intent.md", "references/ledger.md"],
                        }
                    elif state.get("lifecycle", {}).get("phase") == "VERIFY":
                        action = {
                            "kind": "prepare_acceptance_handoff", "subject_refs": [],
                            "preconditions": ["G4 evidence is current and the exact acceptance projection is bound to this candidate"],
                            "read_refs": ["phases/accept.md", "contracts/reviewer.md"],
                        }
                    elif state.get("lifecycle", {}).get("phase") == "ACCEPT":
                        acceptance = state.get("acceptance", [])
                        latest = acceptance[-1] if acceptance else None
                        binding = current_intent_binding(state) if state.get("intent") else None
                        if (
                            latest and latest.get("verdict") == "PASS"
                            and binding and latest.get("intent_revision") == binding["revision"]
                            and not latest.get("invalidated_by")
                            and not any(item.get("impact") == "blocking" and not item.get("invalidated_by") for item in state.get("issues", []))
                            and not active_publication_leases(state)
                            and not any(effect_is_unresolved(item) for item in state.get("operations", []))
                        ):
                            action = {
                                "kind": "finalize_acceptance", "subject_refs": [latest["return_ref"]] if latest.get("return_ref") else [],
                                "preconditions": ["current G5 PASS; supply --gate-id G6 to record terminal acceptance"],
                                "read_refs": ["phases/accept.md", "references/ledger.md"],
                            }
                        else:
                            action = {
                                "kind": "human_input_required", "subject_refs": [],
                                "preconditions": ["fresh current-intent G5 PASS and all blockers, leases, and effects must be resolved"],
                                "read_refs": ["phases/accept.md", "references/ledger.md"],
                                "human_input_required": True,
                            }
                    else:
                        action = {
                            "kind": "human_input_required", "subject_refs": [],
                            "preconditions": ["inspect verified lifecycle and choose the next owner-authorized gate action"],
                            "read_refs": ["phases/start.md", "references/ledger.md"],
                            "human_input_required": True,
                        }
    elif (
        action["kind"].startswith("await_")
        and targets
        and all(item.get("state") in TERMINAL_ATTEMPT_STATES for item in targets)
    ):
        action = {
            "kind": "human_input_required",
            "subject_refs": list(refs),
            "preconditions": ["inspect the recorded terminal attempt outcome; owner must choose a safe next action"],
            "read_refs": ["phases/recover.md", "references/ledger.md"],
            "human_input_required": True,
        }
    if str(action.get("kind", "")).startswith("await_") and not any(
        "not a user checkpoint" in str(item) for item in action.get("preconditions", [])
    ):
        action.setdefault("preconditions", []).insert(0, "internal orchestration wait; not a user checkpoint")
    action["event_id"] = _action_event_id(action.get("kind"))
    action.setdefault("human_input_required", False)
    action["terminal_wait"] = False
    return action


def _blocked_repair_candidate_action(state: dict[str, Any]) -> dict[str, Any] | None:
    """Derive candidate publication for an exact returned owner-authorized repair worker."""
    tickets = {item.get("id"): item for item in state.get("tickets", [])}
    attempts = {item.get("id"): item for item in state.get("attempts", [])}
    findings = {item.get("id"): item for item in state.get("findings", [])}
    issues = {item.get("id"): item for item in state.get("issues", [])}
    for ticket in state.get("tickets", []):
        attempt_ref = ticket.get("last_worker_attempt")
        attempt = attempts.get(attempt_ref)
        contract = attempt.get("repair_contract") if attempt else None
        finding_refs = repair_finding_refs(contract) if isinstance(contract, dict) else []
        if (
            attempt is None
            or attempt.get("kind") != "worker"
            or attempt.get("mode") != "repair"
            or attempt.get("state") != "RETURNED"
            or not attempt.get("return_ref")
            or attempt.get("candidate_sha") is not None
            or attempt.get("candidate_tree_sha") is not None
            or attempt.get("lease", {}).get("state") != "active"
            or attempt.get("subject_ref") != ticket.get("id")
            or ticket.get("current_attempt") != attempt_ref
            or ticket.get("current_worker_attempt") is not None
            or not finding_refs
        ):
            continue
        authorization = repair_authorization_for_attempt(state, ticket["id"], contract, attempt["id"])
        records = [findings.get(ref) or issues.get(ref) for ref in finding_refs]
        if (
            authorization is None
            or attempt.get("repair_authorization_ref") != authorization.get("id")
            or any(
                record is None or record.get("impact") != "blocking" or record.get("invalidated_by")
                or ticket["id"] not in record.get("affected_refs", [])
                for record in records
            )
        ):
            continue
        return {
            "kind": "audit_worker_return_and_prepare_candidate",
            "subject_refs": [ticket["id"], attempt["id"], *finding_refs],
            "preconditions": ["exact latest authorized repair return is validated DONE", "audit its actual write set and prepare the candidate effect without clearing BLOCKED obligations"],
            "read_refs": ["phases/execute.md", "references/safety.md", "references/routing.md"],
        }
    return None


def derive_control_projection(state: dict[str, Any]) -> dict[str, Any]:
    """Shared read projection used by status and publication admission metadata."""
    return {"next_action": derive_next_action(state), "allowed_events": allowed_events(state)}


def refresh_control_projection(state: dict[str, Any]) -> None:
    """Persist the derived projection for Phase B ledgers before validation/publication."""
    if state.get("candidate_model_version") != "1.1":
        return
    projection = derive_control_projection(state)
    state.setdefault("lifecycle", {})["next_action"] = projection["next_action"]
    state["lifecycle"]["allowed_events"] = projection["allowed_events"]


def default_usage() -> dict[str, Any]:
    return {
        "counters": zero_usage(),
        "tokens": None,
        "token_reason": "token_meter_unavailable",
        "unknown_reason": "token meter unavailable on this runtime",
        "trace": [],
        "shared_setup": zero_usage(),
        "gate_costs": {f"G{i}": zero_usage() for i in range(7)},
    }


def ensure_runtime_provenance(state: dict[str, Any]) -> dict[str, Any]:
    """Add effective helper provenance without rewriting run creation history."""
    provenance = state.setdefault("runtime_provenance", {
        "creation_skill_version": state.get("skill_version", "unknown"),
        "current_schema_version": state.get("schema_version", SCHEMA_VERSION),
        "last_mutating_skill_version": SKILL_VERSION,
        "compatibility_floor": COMPATIBILITY_FLOOR,
        "applied_migrations": [],
    })
    provenance.setdefault("creation_skill_version", state.get("skill_version", "unknown"))
    provenance["current_schema_version"] = state.get("schema_version", SCHEMA_VERSION)
    provenance["last_mutating_skill_version"] = SKILL_VERSION
    provenance.setdefault("compatibility_floor", COMPATIBILITY_FLOOR)
    provenance.setdefault("applied_migrations", [])
    return provenance


def semver_tuple(value: Any) -> tuple[int, int, int] | None:
    """Parse strict numeric semantic versions; malformed floors fail closed."""
    if not isinstance(value, str):
        return None
    match = SEMVER_RE.fullmatch(value)
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def mutation_ineligibility(state: dict[str, Any]) -> str | None:
    """Return the read-only reason, or None when this writer may mutate state."""
    if state.get("schema_version") != SCHEMA_VERSION:
        return f"unsupported shape schema {state.get('schema_version')!r}; upgrade with a helper that supports it"
    provenance = state.get("runtime_provenance")
    if not isinstance(provenance, dict):
        return (
            "legacy state has no v1.1 semantic writer metadata; read-only until an "
            "explicit owner-authorized append-only migration to state contract 1.1"
        )
    contract = provenance.get("state_contract_version")
    minimum = provenance.get("minimum_writer_version")
    if contract is None or minimum is None:
        return (
            "legacy state lacks v1.1 semantic contract/minimum writer metadata; read-only until an "
            "explicit owner-authorized append-only migration to state contract 1.1"
        )
    if contract != STATE_CONTRACT_VERSION:
        return (
            f"state contract {contract!r} is not recognized by writer {WRITER_VERSION}; "
            "diagnose read-only and use a compatible upgrade/migration"
        )
    floor = semver_tuple(minimum)
    writer = semver_tuple(WRITER_VERSION)
    if floor is None:
        return f"malformed minimum_writer_version {minimum!r}; mutation is forbidden"
    if writer is None:
        return f"helper writer version {WRITER_VERSION!r} is malformed; mutation is forbidden"
    if writer < floor:
        return f"state requires writer {minimum} or newer; current writer is {WRITER_VERSION}"
    if provenance.get("current_schema_version") != state.get("schema_version"):
        return (
            "runtime provenance current_schema_version does not match ledger schema_version; "
            "repair through an explicit owner-authorized migration"
        )
    if state.get("candidate_model_version") != "1.1" and any(
        state.get(collection) for collection in ("tickets", "attempts", "candidates", "findings")
    ):
        return (
            "populated state lacks the explicit Phase B candidate model marker; read/status/diagnose only "
            "until an explicit owner-authorized append-only migration defines candidate authority"
        )
    return None


def require_mutation_eligible(state: dict[str, Any]) -> None:
    reason = mutation_ineligibility(state)
    if reason is not None:
        fail(f"mutation is read-only: {reason}")


def resolved_run_settings(state: dict[str, Any]) -> dict[str, str]:
    """Return effective settings without migrating legacy ledgers."""
    stored = state.get("run_settings")
    if not isinstance(stored, dict):
        stored = {}
    return {
        "interaction_mode": stored.get("interaction_mode", DEFAULT_RUN_SETTINGS["interaction_mode"]),
        "depth": stored.get("depth", DEFAULT_RUN_SETTINGS["depth"]),
    }


def run_settings_display(settings: dict[str, str]) -> str:
    mode = RUN_SETTING_LABELS["interaction_mode"].get(settings["interaction_mode"], settings["interaction_mode"])
    depth = RUN_SETTING_LABELS["depth"].get(settings["depth"], settings["depth"])
    return f"Режим: {mode} · глубина: {depth}"


def parse_run_settings(request: str | None) -> dict[str, str]:
    """Parse only obvious English/Russian preset phrases; ambiguity defaults."""
    if not request:
        return dict(DEFAULT_RUN_SETTINGS)
    text = re.sub(r"[_/–—-]+", " ", request.casefold())
    full = bool(re.search(r"(?:\bполный\s+автомат(?:ический)?\b|\bполностью\s+автомат(?:ический)?\b|\bfull\s+(?:auto|automatic|automated|automation|mode)\b|\bfully\s+automatic\b)", text))
    semi = bool(re.search(r"(?:\bполуавтомат(?:ический)?\b|\bsemi\s+automatic\b|\bsemi\s+automated\b|\bsemi\s+mode\b)", text))
    deep = bool(re.search(r"(?:\bглубок(?:ая|ий|ое|ую|о)?\b|\bdeep\b|\bin\s+depth\b|\bthorough\b|\bdetailed\b)", text))
    normal = bool(re.search(r"(?:\bобычн(?:ая|ый|ое|ую|о)?\b|\bnormal\b|\bstandard\b|\bbaseline\b)", text))
    return {
        "interaction_mode": "full" if full and not semi else DEFAULT_RUN_SETTINGS["interaction_mode"],
        "depth": "deep" if deep and not normal else DEFAULT_RUN_SETTINGS["depth"],
    }


def run_settings_from_args(request: str | None, interaction_mode: str | None, depth: str | None) -> dict[str, str]:
    settings = parse_run_settings(request)
    if interaction_mode is not None:
        settings["interaction_mode"] = interaction_mode
    if depth is not None:
        settings["depth"] = depth
    return settings


def routing_intent(state: dict[str, Any]) -> dict[str, Any]:
    """Expose preset intent to routing without binding or selecting a model."""
    settings = resolved_run_settings(state)
    return {"interaction_mode": settings["interaction_mode"], "depth": settings["depth"], "model_binding": None}


def add_usage(target: dict[str, int], delta: dict[str, Any]) -> None:
    for field in USAGE_FIELDS:
        value = delta.get(field, 0)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            fail(f"usage delta {field} must be a non-negative integer")
        target[field] = target.get(field, 0) + value


def current_intent_binding(state: dict[str, Any]) -> dict[str, str]:
    intent = state.get("intent")
    if not isinstance(intent, dict):
        fail("current intent is missing")
    document_ref = intent.get("document_ref")
    document = next((item for item in state.get("documents", []) if item.get("id") == document_ref), None)
    if document is None:
        fail("current intent document is missing")
    path = Path(document.get("path", ""))
    if not path.exists() or path.is_symlink() or not path.is_file():
        fail("current intent document is unavailable")
    actual_hash = sha256_file(path)
    if actual_hash != document.get("hash"):
        fail("current intent document hash does not match the ledger")
    expected_hash = intent.get("document_hash")
    if expected_hash is not None and expected_hash != actual_hash:
        fail("current intent document hash does not match intent binding")
    return {"revision": str(intent.get("current_revision")), "document_ref": str(document_ref), "document_hash": actual_hash}


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def safe_id(value: str, label: str = "id") -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        fail(f"invalid {label}: expected path-safe identifier")
    return value


def safe_root(path: str | Path, label: str) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_symlink():
        fail(f"{label} may not be a symlink")
    result = candidate.resolve()
    if result == Path(result.anchor):
        fail(f"{label} may not be filesystem root")
    return result


def under(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def regular_non_symlink(path: Path) -> None:
    try:
        mode = path.lstat().st_mode
    except OSError as exc:
        fail(f"expected regular non-symlink file: {path}: {exc}")
    if not stat.S_ISREG(mode):
        fail(f"expected regular non-symlink file: {path}")


def regular_directory(path: Path, label: str = "directory") -> None:
    if path.is_symlink() or not path.is_dir():
        fail(f"expected regular non-symlink {label}: {path}")


def relative_path(value: str, label: str = "path") -> str:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        fail(f"invalid {label}: expected repository-relative path")
    path = Path(value)
    if ".." in path.parts:
        fail(f"invalid {label}: path traversal is not allowed")
    return path.as_posix()


def read_json(path: Path, label: str = "JSON") -> Any:
    regular_non_symlink(path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        fail(f"invalid {label} {path}: {exc}")


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temp.exists():
            temp.unlink()


def atomic_create(path: Path, data: bytes) -> bool:
    """Create one immutable file without replacing a concurrently-created path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temp, path, follow_symlinks=False)
            created = True
        except FileExistsError:
            regular_non_symlink(path)
            if path.read_bytes() != data:
                fail(f"immutable destination already exists with different bytes: {path}")
            created = False
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temp.exists():
            temp.unlink()
    return created


class Lock:
    def __init__(self, path: Path):
        self.path = path
        self.stream = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open("a+")
        fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, *_args):
        if self.stream is not None:
            fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
            self.stream.close()


def schema_path() -> Path:
    return Path(__file__).resolve().parents[1] / "schemas" / "contracts.schema.json"


def schema() -> dict[str, Any]:
    try:
        return json.loads(schema_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"schema unavailable or malformed: {exc}")


def validate(value: Any, spec: dict[str, Any], root: dict[str, Any], path: str = "$", seen: set[str] | None = None) -> None:
    """Validate the closed subset used by this package; unknown keywords fail closed."""
    supported = {"$schema", "$id", "$defs", "title", "$ref", "oneOf", "allOf", "if", "then", "type", "required", "properties", "additionalProperties", "items", "enum", "const", "pattern", "minLength", "minItems", "maxItems", "uniqueItems", "minimum", "minProperties"}
    unknown = set(spec) - supported
    if unknown:
        fail(f"unsupported schema keyword(s) at {path}: {sorted(unknown)}")
    if "$ref" in spec:
        ref = spec["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/$defs/"):
            fail(f"unsupported schema ref at {path}: {ref}")
        name = ref.rsplit("/", 1)[-1]
        validate(value, root.get("$defs", {}).get(name, {}), root, path, seen)
        return
    if "oneOf" in spec:
        successes = 0
        for branch in spec["oneOf"]:
            try:
                validate(value, branch, root, path, seen)
            except LedgerError:
                continue
            successes += 1
        if successes != 1:
            fail(f"{path}: expected exactly one matching schema branch; matched {successes}")
    for branch in spec.get("allOf", []):
        validate(value, branch, root, path, seen)
    if "if" in spec:
        try:
            validate(value, spec["if"], root, path, seen)
            condition_matches = True
        except LedgerError:
            condition_matches = False
        if condition_matches and "then" in spec:
            validate(value, spec["then"], root, path, seen)
    if "const" in spec and value != spec["const"]:
        fail(f"{path}: expected constant {spec['const']!r}")
    if "enum" in spec and value not in spec["enum"]:
        fail(f"{path}: value {value!r} is not in enum")
    types = spec.get("type")
    if types:
        allowed = [types] if isinstance(types, str) else types
        ok = any({"object": isinstance(value, dict), "array": isinstance(value, list), "string": isinstance(value, str), "integer": isinstance(value, int) and not isinstance(value, bool), "number": isinstance(value, (int, float)) and not isinstance(value, bool), "boolean": isinstance(value, bool), "null": value is None}.get(t, False) for t in allowed)
        if not ok:
            fail(f"{path}: wrong type")
    if isinstance(value, str):
        if len(value) < spec.get("minLength", 0):
            fail(f"{path}: shorter than minLength")
        if "pattern" in spec and not re.fullmatch(spec["pattern"], value):
            fail(f"{path}: pattern mismatch")
    if isinstance(value, (int, float)) and value < spec.get("minimum", value):
        fail(f"{path}: below minimum")
    if isinstance(value, list):
        if len(value) < spec.get("minItems", 0):
            fail(f"{path}: fewer than minItems")
        if len(value) > spec.get("maxItems", len(value)):
            fail(f"{path}: more than maxItems")
        if spec.get("uniqueItems") and len({canonical_bytes(item) for item in value}) != len(value):
            fail(f"{path}: duplicate array items")
        if "items" in spec:
            for index, item in enumerate(value):
                validate(item, spec["items"], root, f"{path}[{index}]")
    if isinstance(value, dict):
        if len(value) < spec.get("minProperties", 0):
            fail(f"{path}: fewer than minProperties")
        for required in spec.get("required", []):
            if required not in value:
                fail(f"{path}: missing required field {required}")
        properties = spec.get("properties", {})
        if spec.get("additionalProperties") is False:
            extras = set(value) - set(properties)
            if extras:
                fail(f"{path}: unknown field(s): {sorted(extras)}")
        for key, child in properties.items():
            if key in value:
                validate(value[key], child, root, f"{path}.{key}")


def validate_ledger(state: dict[str, Any], *, verify_files: bool = True) -> None:
    root = schema()
    validate(state, root, root)
    if state["run_id"] != Path(state["repository"]["control_root"]).name and state["run_id"] == "":
        fail("run_id must be nonempty")
    ids: set[str] = set()
    for collection in ("documents", "requirements", "criteria", "contracts", "decisions", "tickets", "candidates", "attempts", "issues", "findings", "reviews", "review_qualifications", "repair_waves", "operations", "capabilities", "routes", "evidence", "invalidations", "binding_normalizations", "finding_binding_reconciliations"):
        for item in state.get(collection, []):
            if "id" in item:
                if item["id"] in ids:
                    fail(f"duplicate immutable ID: {item['id']}")
                ids.add(item["id"])
    publication = state.get("design_publication")
    history = state.get("design_publication_history", [])
    history_ids: set[str] = set()
    for historical in history:
        if historical["id"] in history_ids or historical["id"] in ids:
            fail(f"duplicate immutable design publication ID: {historical['id']}")
        history_ids.add(historical["id"])
        ids.add(historical["id"])
    if publication:
        if publication["id"] in ids and publication["id"] not in history_ids:
            fail(f"duplicate immutable ID: {publication['id']}")
        if publication["id"] in history_ids:
            latest = history[-1] if history else None
            if latest is None or latest != publication:
                fail("current design publication does not match the latest history item")
        else:
            ids.add(publication["id"])
    ticket_ids = {item["id"] for item in state.get("tickets", [])}
    criterion_ids = {item["id"] for item in state.get("criteria", [])}
    requirement_ids = {item["id"] for item in state.get("requirements", [])}
    document_ids = {item["id"] for item in state.get("documents", [])}
    if state.get("intent"):
        intent = state["intent"]
        if intent["document_ref"] not in document_ids:
            fail("intent references unknown document")
        if intent.get("document_hash"):
            document = next(item for item in state.get("documents", []) if item["id"] == intent["document_ref"])
            if document.get("hash") != intent["document_hash"]:
                fail("intent document_hash does not match document")
    if publication and publication.get("status") == "PUBLISHED":
        if not state.get("intent"):
            fail("design publication requires a current intent")
        intent = state["intent"]
        if publication["intent_revision"] != intent.get("current_revision") or publication["intent_document_ref"] != intent.get("document_ref") or publication["intent_document_hash"] != intent.get("document_hash"):
            fail("design publication is bound to a stale intent")
        refs = set(publication["document_refs"])
        if not refs or not refs.issubset(document_ids):
            fail("design publication references an unknown document")
        if not set(publication["contract_refs"]).issubset({item["id"] for item in state.get("contracts", [])}):
            fail("design publication references an unknown contract")
        if not set(publication["ticket_refs"]).issubset({item["id"] for item in state.get("tickets", [])}):
            fail("design publication references an unknown ticket")
        if not set(publication["route_refs"]).issubset({item["id"] for item in state.get("routes", [])}):
            fail("design publication references an unknown route")
        if not set(publication.get("requirement_refs", [])).issubset(requirement_ids):
            fail("design publication references an unknown requirement")
        if not set(publication.get("criterion_refs", [])).issubset(criterion_ids):
            fail("design publication references an unknown criterion")
        for document in state.get("documents", []):
            if document["id"] in refs:
                path = Path(document["path"])
                if verify_files and (not path.exists() or path.is_symlink() or not path.is_file() or sha256_file(path) != document["hash"]):
                    fail(f"published design document is unavailable or drifted: {document['id']}")
    for historical in history:
        if historical["bundle_ref"] != f"objects/{historical['publication_hash']}":
            fail(f"design publication history bundle reference does not match its fingerprint: {historical['id']}")
        refs = set(historical["document_refs"])
        if not refs or not refs.issubset(document_ids):
            fail("design publication history references an unknown document")
        if not set(historical["contract_refs"]).issubset({item["id"] for item in state.get("contracts", [])}):
            fail("design publication history references an unknown contract")
        if not set(historical["ticket_refs"]).issubset({item["id"] for item in state.get("tickets", [])}):
            fail("design publication history references an unknown ticket")
        if not set(historical["route_refs"]).issubset({item["id"] for item in state.get("routes", [])}):
            fail("design publication history references an unknown route")
        if not set(historical.get("requirement_refs", [])).issubset(requirement_ids):
            fail("design publication history references an unknown requirement")
        if not set(historical.get("criterion_refs", [])).issubset(criterion_ids):
            fail("design publication history references an unknown criterion")
        if verify_files:
            for document in state.get("documents", []):
                if document["id"] in refs:
                    path = Path(document["path"])
                    if not path.exists() or path.is_symlink() or not path.is_file() or sha256_file(path) != document["hash"]:
                        fail(f"historical design document is unavailable or drifted: {document['id']}")
    publication_records = history or ([publication] if publication else [])
    for record in publication_records:
        if record["bundle_ref"] != f"objects/{record['publication_hash']}":
            fail(f"design publication bundle reference does not match its fingerprint: {record['id']}")
        if verify_files:
            object_path = Path(state["repository"]["control_root"]) / ".autopilot" / "runs" / state["run_id"] / record["bundle_ref"]
            if not object_path.exists() or object_path.is_symlink() or not object_path.is_file() or sha256_file(object_path) != record["publication_hash"]:
                fail(f"design publication bundle object is unavailable or drifted: {record['id']}")
    for requirement in state.get("requirements", []):
        if any(ref not in criterion_ids for ref in requirement.get("criterion_refs", [])):
            fail(f"requirement references unknown criterion: {requirement['id']}")
    for criterion in state.get("criteria", []):
        if any(ref not in requirement_ids for ref in criterion.get("requirement_refs", [])):
            fail(f"criterion references unknown requirement: {criterion['id']}")
    requirement_publication_ids: set[str] = set()
    for record in state.get("requirements_publications", []):
        if record["id"] in requirement_publication_ids or record["id"] in ids:
            fail(f"duplicate immutable requirements publication ID: {record['id']}")
        requirement_publication_ids.add(record["id"])
        ids.add(record["id"])
        if not set(record["requirement_refs"]).issubset(requirement_ids):
            fail(f"requirements publication references an unknown requirement: {record['id']}")
        if not set(record["criterion_refs"]).issubset(criterion_ids):
            fail(f"requirements publication references an unknown criterion: {record['id']}")
        if record["manifest_ref"] != f"objects/{record['publication_hash']}":
            fail(f"requirements publication object reference does not match its hash: {record['id']}")
        if verify_files:
            object_path = Path(state["repository"]["control_root"]) / ".autopilot" / "runs" / state["run_id"] / record["manifest_ref"]
            if not object_path.exists() or object_path.is_symlink() or not object_path.is_file() or sha256_file(object_path) != record["publication_hash"]:
                fail(f"requirements publication object is unavailable or drifted: {record['id']}")
    if publication and publication.get("requirements_publication_ref") is not None:
        requirements_record = next((item for item in state.get("requirements_publications", []) if item.get("id") == publication["requirements_publication_ref"]), None)
        if requirements_record is None:
            fail("design publication references an unknown requirements publication")
        if requirements_record.get("intent_revision") != publication.get("intent_revision") or requirements_record.get("intent_document_hash") != publication.get("intent_document_hash"):
            fail("design publication requirements binding is stale")
    for ticket in state.get("tickets", []):
        if any(ref not in criterion_ids for ref in ticket.get("criterion_refs", [])):
            fail(f"ticket references unknown criterion: {ticket['id']}")
    graph = {item["id"]: set(item.get("dependency_refs", [])) for item in state.get("tickets", [])}
    if any(dep not in ticket_ids for deps in graph.values() for dep in deps):
        fail("ticket dependency references unknown ticket")
    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(node: str) -> None:
        if node in visiting:
            fail("ticket dependency graph contains a cycle")
        if node in visited:
            return
        visiting.add(node)
        for dep in graph[node]:
            visit(dep)
        visiting.remove(node)
        visited.add(node)
    for node in graph:
        visit(node)
    for attempt in state.get("attempts", []):
        if attempt["epoch"] > state["owner"]["epoch"] + 1:
            fail(f"attempt epoch is ahead of owner epoch: {attempt['id']}")
        runtime = attempt.get("runtime")
        if isinstance(runtime, dict):
            expected_spawn_id = stable_spawn_request_id(
                state.get("run_id", ""), attempt["id"], attempt["epoch"], attempt.get("packet_hash", ""),
            )
            refs = set(runtime.get("observation_refs", []))
            if runtime.get("spawn_request_id") != expected_spawn_id:
                fail(f"runtime spawn request ID is not stable for attempt {attempt['id']}")
            if any(ref and ref not in refs for ref in (
                runtime.get("start_ref"), runtime.get("stop_ref"), runtime.get("not_started_ref"),
                runtime.get("return_observation_ref"),
            )) or not set(runtime.get("heartbeat_refs", [])).issubset(refs):
                fail(f"runtime observation pointers are inconsistent for attempt {attempt['id']}")
            liveness = runtime.get("liveness")
            if liveness == "running" and (not runtime.get("start_ref") or not runtime.get("runtime_instance_id")):
                fail(f"running runtime attempt lacks its exact start/instance binding: {attempt['id']}")
            if liveness == "stopped" and (not runtime.get("stop_ref") or not runtime.get("runtime_instance_id")):
                fail(f"stopped runtime attempt lacks its exact stop/instance binding: {attempt['id']}")
            if liveness == "not_started" and (not runtime.get("not_started_ref") or runtime.get("runtime_instance_id") is not None):
                fail(f"not_started runtime attempt has an invalid instance binding: {attempt['id']}")
        if (
            state.get("runtime_provenance") and attempt.get("kind") == "review"
            and attempt.get("state") == "RETURNED" and attempt.get("lease", {}).get("state") == "active"
            and (not isinstance(attempt.get("runtime"), dict) or runtime_liveness(attempt) in ("stopped", "not_started"))
        ):
            fail(f"returned legacy reviewer attempt or stopped runtime reviewer retains an active lease: {attempt['id']}")
    attempts_by_id = {item["id"]: item for item in state.get("attempts", [])}
    candidates_by_id = {item["id"]: item for item in state.get("candidates", [])}
    operations_by_id = {item["id"]: item for item in state.get("operations", [])}
    reviews_by_id = {item["id"]: item for item in state.get("reviews", [])}
    qualifications_by_id = {item["id"]: item for item in state.get("review_qualifications", [])}
    for qualification in state.get("review_qualifications", []):
        review_refs = qualification.get("accepted_review_refs", [])
        accepted_reviews = [reviews_by_id.get(ref) for ref in review_refs]
        if any(item is None or item.get("accepted") is not True for item in accepted_reviews):
            fail(f"review qualification references a missing or unaccepted review: {qualification['id']}")
        if [item.get("return_ref") for item in accepted_reviews] != qualification.get("accepted_return_refs", []):
            fail(f"review qualification return refs do not match accepted reviews: {qualification['id']}")
        if [item.get("integrity_ref") for item in accepted_reviews] != qualification.get("integrity_refs", []):
            fail(f"review qualification integrity refs do not match accepted reviews: {qualification['id']}")
        if any(item.get("subject_fingerprint") != qualification.get("subject_fingerprint") for item in accepted_reviews):
            fail(f"review qualification mixes subject fingerprints: {qualification['id']}")
        accepted_attempts = [attempts_by_id.get(item.get("attempt_ref")) for item in accepted_reviews]
        if any(
            attempt is None
            or attempt.get("state") != "RETURNED"
            or attempt.get("lease", {}).get("state") != "released"
            or attempt.get("return_ref") != review.get("return_ref")
            or attempt.get("subject_ref") != qualification.get("subject_ref")
            or attempt.get("review_purpose") not in (None, review.get("purpose"))
            for review, attempt in zip(accepted_reviews, accepted_attempts)
        ):
            fail(f"review qualification is not bound to exact terminal review attempts: {qualification['id']}")
        attempt_refs = [item.get("attempt_ref") for item in accepted_reviews]
        if len(attempt_refs) != len(set(attempt_refs)):
            fail(f"review qualification reuses one attempt for multiple accepted reviews: {qualification['id']}")
        if any(item.get("purpose") not in qualification.get("required_purposes", []) for item in accepted_reviews):
            fail(f"review qualification includes a review outside its required purposes: {qualification['id']}")
        if any(item.get("intent_revision") != qualification.get("intent_revision") for item in accepted_reviews):
            fail(f"review qualification mixes intent revisions: {qualification['id']}")
        satisfied = sorted({item.get("purpose") for item in accepted_reviews if item.get("verdict") == "PASS"})
        blocked = any(item.get("verdict") in ("BLOCK", "UNVERIFIABLE") for item in accepted_reviews)
        expected_result = "BLOCK" if blocked else (
            "PASS" if set(qualification.get("required_purposes", [])).issubset(satisfied) else "INCOMPLETE"
        )
        if qualification.get("satisfied_purposes") != satisfied or qualification.get("result") != expected_result:
            fail(f"review qualification result is not derived from immutable accepted reviews: {qualification['id']}")
    finding_ids = {item.get("id") for item in state.get("findings", [])}
    for wave in state.get("repair_waves", []):
        source = qualifications_by_id.get(wave.get("source_qualification_ref"))
        if source is None or source.get("result") != "BLOCK" or source.get("required_purposes") != ["final_g5"]:
            fail(f"repair wave source is not a BLOCK final-G5 qualification: {wave['id']}")
        if not set(wave.get("finding_refs", [])).issubset(finding_ids):
            fail(f"repair wave references unknown findings: {wave['id']}")
        if wave.get("state") == "CLOSED":
            final = qualifications_by_id.get(wave.get("final_g5_qualification_ref"))
            if (
                final is None or final.get("result") != "PASS"
                or final.get("required_purposes") != ["final_g5"]
                or final.get("subject_fingerprint") != wave.get("repaired_candidate_fingerprint")
                or final.get("subject_fingerprint") == wave.get("source_candidate_fingerprint")
            ):
                fail(f"closed repair wave lacks a fresh final-G5 qualification: {wave['id']}")
        elif wave.get("final_g5_qualification_ref") is not None or wave.get("repaired_candidate_fingerprint") is not None:
            fail(f"open repair wave contains terminal qualification linkage: {wave['id']}")
    for candidate in state.get("candidates", []):
        ticket = next((item for item in state.get("tickets", []) if item.get("id") == candidate.get("ticket_ref")), None)
        producer = next((item for item in state.get("attempts", []) if item.get("id") == candidate.get("producer_attempt_ref")), None)
        if ticket is None or producer is None or producer.get("subject_ref") != candidate.get("ticket_ref") or producer.get("kind") != "worker":
            fail(f"candidate has no exact same-ticket worker producer: {candidate['id']}")
        if producer.get("candidate_sha") != candidate.get("sha") or producer.get("candidate_tree_sha") != candidate.get("tree_sha"):
            fail(f"candidate identity does not match its immutable producer attempt: {candidate['id']}")
        parent_ref = candidate.get("parent_candidate_ref")
        if parent_ref is not None:
            parent = candidates_by_id.get(parent_ref)
            if parent is None or parent.get("ticket_ref") != candidate.get("ticket_ref"):
                fail(f"candidate parent is missing or belongs to another ticket: {candidate['id']}")
        if candidate.get("superseded_by") is not None:
            successor = candidates_by_id.get(candidate["superseded_by"])
            if successor is None or successor.get("parent_candidate_ref") != candidate["id"]:
                fail(f"candidate supersession edge is not reciprocal: {candidate['id']}")
        qualification_ref = candidate.get("qualification_ref")
        if qualification_ref is not None:
            qualification = qualifications_by_id.get(qualification_ref)
            if (
                qualification is None
                or qualification.get("subject_ref") != candidate.get("ticket_ref")
                or qualification.get("subject_fingerprint") != candidate.get("sha")
                or qualification.get("result") != "PASS"
            ):
                fail(f"candidate qualification does not authorize this exact candidate: {candidate['id']}")
        proof_ref = candidate.get("proof_ref")
        if proof_ref is not None:
            if producer.get("candidate_proof_ref") != proof_ref:
                fail(f"candidate and producer do not share one verified proof: {candidate['id']}")
            proof_operations = [
                operation for operation in operations_by_id.values()
                if operation.get("proof_ref") == proof_ref and operation.get("candidate_ref") == candidate["id"]
            ]
            if len(proof_operations) != 1 or proof_operations[0].get("state") != "finalized":
                fail(f"candidate proof is not linked to exactly one finalized effect: {candidate['id']}")
    for ticket in state.get("tickets", []):
        candidate_ref = ticket.get("current_candidate")
        if candidate_ref is not None:
            candidate = candidates_by_id.get(candidate_ref)
            if candidate is None or candidate.get("ticket_ref") != ticket.get("id"):
                fail(f"ticket current_candidate does not identify a current same-ticket candidate: {ticket['id']}")
        worker_ref = ticket.get("current_worker_attempt")
        if worker_ref is not None:
            worker = next((item for item in state.get("attempts", []) if item.get("id") == worker_ref), None)
            if worker is None or worker.get("kind") != "worker" or worker.get("subject_ref") != ticket.get("id") or worker.get("state") not in ("PREPARED", "DISPATCHED"):
                fail(f"ticket current_worker_attempt must identify its in-flight worker: {ticket['id']}")
        last_worker_ref = ticket.get("last_worker_attempt")
        if last_worker_ref is not None:
            worker = next((item for item in state.get("attempts", []) if item.get("id") == last_worker_ref), None)
            if worker is None or worker.get("kind") != "worker" or worker.get("subject_ref") != ticket.get("id"):
                fail(f"ticket last_worker_attempt must identify a same-ticket worker: {ticket['id']}")
        if state.get("candidate_model_version") == "1.1" and ticket.get("last_worker_attempt") is not None and ticket.get("current_attempt") != ticket.get("last_worker_attempt"):
            fail(f"Phase B current_attempt compatibility alias diverges from last_worker_attempt: {ticket['id']}")
    if state["lifecycle"]["control"] == "ACCEPTED":
        if not any(a.get("verdict") == "PASS" for a in state.get("acceptance", [])):
            fail("ACCEPTED requires a recorded G5 PASS")
        latest = state.get("acceptance", [])[-1] if state.get("acceptance") else None
        if (
            state.get("review_model_version") == "1.1"
            and latest
            and (latest.get("purpose") == "final_g5" or latest.get("qualification_ref") is not None)
        ):
            matching = [
                item for item in state.get("review_qualifications", [])
                if item.get("result") == "PASS"
                and item.get("required_purposes") == ["final_g5"]
                and latest
                and item.get("id") == latest.get("qualification_ref")
                and item.get("subject_fingerprint") == latest.get("candidate_fingerprint")
                and latest.get("return_ref") in item.get("accepted_return_refs", [])
            ]
            if not matching:
                fail("ACCEPTED requires the immutable current final-G5 qualification")
            if any(item.get("state") == "OPEN" for item in state.get("repair_waves", [])):
                fail("ACCEPTED requires every final-G5 repair wave to be closed")
    for operation in state.get("operations", []):
        if operation.get("state") == "applied" and not operation.get("receipt_ref"):
            fail(f"applied operation lacks receipt: {operation['id']}")
        linkage = (
            operation.get("proof_ref"), operation.get("candidate_ref"),
            operation.get("finalized_revision"),
        )
        if operation.get("state") == "finalized":
            if not operation.get("receipt_ref") or any(value is None for value in linkage):
                fail(f"finalized operation lacks receipt/candidate/proof linkage: {operation['id']}")
            if not re.fullmatch(r"objects/[0-9a-f]{64}", operation.get("receipt_ref", "")):
                fail(f"finalized operation receipt is not immutable: {operation['id']}")
            candidate = candidates_by_id.get(operation.get("candidate_ref"))
            if candidate is None or candidate.get("proof_ref") != operation.get("proof_ref"):
                fail(f"finalized operation does not identify its verified candidate: {operation['id']}")
            producer = attempts_by_id.get(candidate.get("producer_attempt_ref"))
            if producer is None or producer.get("candidate_proof_ref") != operation.get("proof_ref"):
                fail(f"finalized operation candidate producer has different proof: {operation['id']}")
            if operation.get("finalized_revision") > state.get("revision", -1):
                fail(f"finalized operation revision is ahead of the ledger: {operation['id']}")
        elif any(value is not None for value in linkage):
            fail(f"non-finalized operation contains finalized candidate linkage: {operation['id']}")
    all_ids = ids
    for finding in state.get("findings", []):
        if any(ref not in all_ids for ref in finding.get("affected_refs", [])):
            fail(f"finding references unknown subject: {finding['id']}")
    for invalidation in state.get("invalidations", []):
        if invalidation.get("amendment_ref") not in all_ids:
            # The amendment itself is an event ID, not a regular collection
            # member; validate its shape while allowing it to be new.
            safe_id(invalidation.get("amendment_ref"), "amendment_id")
        if any(ref not in all_ids for ref in invalidation.get("consumer_refs", [])):
            fail(f"invalidation references unknown consumer: {invalidation['id']}")
    publication_by_id = {item.get("id"): item for item in [*history, *([publication] if publication else [])]}
    migration_ids: set[str] = set()
    normalized_pairs: set[tuple[str, str, str, str]] = set()
    for event in state.get("binding_normalizations", []):
        migration_id = event.get("migration_id")
        if migration_id in migration_ids:
            fail(f"duplicate binding normalization migration ID: {migration_id}")
        migration_ids.add(migration_id)
        if (
            event.get("source_revision", -1) >= event.get("applied_revision", -1)
            or event.get("applied_revision", -1) > state.get("revision", -1)
            or event.get("owner_epoch", -1) > state.get("owner", {}).get("epoch", -1)
            or event.get("manifest_ref") != f"objects/{event.get('manifest_hash')}"
        ):
            fail(f"binding normalization event has invalid source/applied revision, epoch, or manifest binding: {event.get('id')}")
        bound_publication = publication_by_id.get(event.get("publication_ref"))
        if bound_publication is None or bound_publication.get("publication_hash") != event.get("publication_hash"):
            fail(f"binding normalization references an unknown or drifted publication: {event.get('id')}")
        for binding in event.get("bindings", []):
            pair = (event["publication_ref"], event["publication_hash"], binding.get("ticket_ref"), binding.get("contract_ref"))
            if pair in normalized_pairs:
                fail(f"overlapping binding normalization pair: {pair[2]} / {pair[3]}")
            normalized_pairs.add(pair)
            ticket = next((item for item in state.get("tickets", []) if item.get("id") == binding.get("ticket_ref")), None)
            contract = next((item for item in state.get("contracts", []) if item.get("id") == binding.get("contract_ref")), None)
            if (
                ticket is None or contract is None
                or binding.get("original_refs") != [binding.get("ticket_ref"), binding.get("contract_ref")]
                or binding.get("contract_ref") not in ticket.get("contract_refs", [])
                or binding.get("ticket_ref") not in contract.get("producer_refs", [])
            ):
                fail(f"binding normalization no longer identifies its exact original self-input pair: {event.get('id')}")
        if verify_files:
            manifest_path = Path(state["repository"]["control_root"]) / ".autopilot" / "runs" / state["run_id"] / event["manifest_ref"]
            regular_non_symlink(manifest_path)
            manifest_raw = manifest_path.read_bytes()
            if sha256_bytes(manifest_raw) != event.get("manifest_hash"):
                fail(f"binding normalization manifest hash mismatch: {event.get('id')}")
            try:
                manifest = json.loads(manifest_raw.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as exc:
                fail(f"binding normalization manifest is invalid JSON: {exc}")
            if (
                manifest.get("migration_id") != migration_id
                or manifest.get("source_revision") != event.get("source_revision")
                or manifest.get("source_ledger_hash") != event.get("source_ledger_hash")
                or manifest.get("owner_epoch") != event.get("owner_epoch")
                or manifest.get("publication_ref") != event.get("publication_ref")
                or manifest.get("publication_hash") != event.get("publication_hash")
                or manifest.get("bindings") != event.get("bindings")
            ):
                fail(f"binding normalization manifest does not reproduce its append-only event: {event.get('id')}")
    reconciliation_ids: set[str] = set()
    reconciled_reviews: set[str] = set()
    reconciled_findings: set[str] = set()
    for event in state.get("finding_binding_reconciliations", []):
        reconciliation_id = event.get("reconciliation_id")
        if reconciliation_id in reconciliation_ids:
            fail(f"duplicate finding binding reconciliation ID: {reconciliation_id}")
        reconciliation_ids.add(reconciliation_id)
        if (
            event.get("source_revision", -1) >= event.get("applied_revision", -1)
            or event.get("applied_revision", -1) > state.get("revision", -1)
            or event.get("owner_epoch", -1) > state.get("owner", {}).get("epoch", -1)
            or event.get("manifest_ref") != f"objects/{event.get('manifest_hash')}"
        ):
            fail(f"finding reconciliation has invalid source/applied revision, epoch, or manifest binding: {event.get('id')}")
        ticket = next((item for item in state.get("tickets", []) if item.get("id") == event.get("ticket_ref")), None)
        candidate = candidates_by_id.get(event.get("candidate_ref"))
        attempt = attempts_by_id.get(event.get("review_attempt_ref"))
        if (
            ticket is None or candidate is None or attempt is None
            or candidate.get("ticket_ref") != ticket.get("id")
            or candidate.get("sha") != event.get("candidate_sha")
            or candidate.get("tree_sha") != event.get("candidate_tree_sha")
            or attempt.get("kind") != "review" or attempt.get("subject_ref") != ticket.get("id")
            or attempt.get("candidate_sha") != event.get("candidate_sha")
            or attempt.get("packet_ref") != event.get("packet_ref")
            or attempt.get("packet_hash") != event.get("packet_hash")
            or attempt.get("return_ref") != event.get("return_ref")
            or event.get("review_attempt_ref") in reconciled_reviews
        ):
            fail(f"finding reconciliation is not bound to its exact ticket/candidate/review attempt: {event.get('id')}")
        reconciled_reviews.add(event["review_attempt_ref"])
        event_finding_refs: set[str] = set()
        event_issue_refs: set[str] = set()
        for binding in event.get("finding_bindings", []):
            finding_ref, issue_ref = binding.get("finding_ref"), binding.get("issue_ref")
            finding = next((item for item in state.get("findings", []) if item.get("id") == finding_ref), None)
            issue = next((item for item in state.get("issues", []) if item.get("id") == issue_ref), None)
            if (
                finding is None or issue is None or finding_ref in event_finding_refs
                or issue_ref in event_issue_refs or finding_ref in reconciled_findings
                or finding.get("source_ref") != attempt.get("id")
                or issue.get("finding_ref") != finding_ref
                or issue.get("source_ref") != attempt.get("id")
                or issue.get("impact") != "blocking" or issue.get("invalidated_by")
                or finding.get("impact") != "blocking" or finding.get("invalidated_by")
                or set(issue.get("affected_refs", [])) != set(finding.get("affected_refs", []))
            ):
                fail(f"finding reconciliation issue mirror is missing, stale, or incompatible: {event.get('id')}")
            event_finding_refs.add(finding_ref)
            event_issue_refs.add(issue_ref)
        if not event_finding_refs:
            fail(f"finding reconciliation has no bindings: {event.get('id')}")
        reconciled_findings.update(event_finding_refs)
        if verify_files:
            event_path = Path(state["repository"]["control_root"]) / ".autopilot" / "runs" / state["run_id"] / event["manifest_ref"]
            regular_non_symlink(event_path)
            event_raw = event_path.read_bytes()
            if sha256_bytes(event_raw) != event.get("manifest_hash"):
                fail(f"finding reconciliation manifest hash mismatch: {event.get('id')}")
            try:
                manifest = json.loads(event_raw.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as exc:
                fail(f"finding reconciliation manifest is invalid JSON: {exc}")
            if any(manifest.get(key) != event.get(key) for key in (
                "reconciliation_id", "source_revision", "source_ledger_hash", "owner_epoch",
                "review_attempt_ref", "ticket_ref", "candidate_ref", "candidate_sha",
                "candidate_tree_sha", "packet_ref", "packet_hash", "return_ref", "return_hash",
                "continuation_receipt_ref", "continuation_receipt_hash", "finding_bindings",
            )):
                fail(f"finding reconciliation manifest does not reproduce its append-only event: {event.get('id')}")
    if verify_files and state.get("finding_binding_reconciliations"):
        p = paths(state["repository"]["control_root"], state["run_id"])
        for event in state["finding_binding_reconciliations"]:
            receipt = stored_payload(p, event["continuation_receipt_ref"], "finding reconciliation continuation receipt")
            blocker_ref = receipt.get("blocker_ref")
            blocker = next((item for item in state.get("issues", []) if item.get("id") == blocker_ref), None)
            candidate = candidates_by_id.get(event.get("candidate_ref"))
            if (
                receipt.get("blocker_scope") != "external" or blocker is None
                or blocker.get("impact") != "blocking" or blocker.get("invalidated_by")
                or blocker_ref not in (candidate or {}).get("blocker_refs", [])
            ):
                fail(f"finding reconciliation lost its exact current external continuation blocker: {event.get('id')}")
    usage = state.get("usage")
    if usage and usage.get("tokens") is None and not usage.get("token_reason"):
        fail("usage with tokens=null requires token_reason")
    provenance = state.get("runtime_provenance")
    if provenance:
        if provenance.get("creation_skill_version") != state.get("skill_version"):
            fail("runtime provenance must preserve the run creation skill version")
        if provenance.get("current_schema_version") != state.get("schema_version"):
            fail("runtime provenance schema version does not match the ledger")
        migration_ids = [item["id"] for item in provenance.get("applied_migrations", [])]
        if len(migration_ids) != len(set(migration_ids)):
            fail("runtime provenance contains duplicate migration IDs")


def paths(control_root: str | Path, run_id: str) -> dict[str, Path]:
    root = safe_root(control_root, "control root")
    safe_id(run_id, "run_id")
    base = root / ".autopilot"
    if base.is_symlink():
        fail("canonical .autopilot namespace may not be a symlink")
    run = base / "runs" / run_id
    return {"root": root, "base": base, "run": run, "ledger": run / "ledger.json", "prev": run / "ledger.prev.json", "lock": base / "owner.lock", "objects": run / "objects", "packets": run / "packets", "docs": run / "docs", "scratch": base / "scratch" / run_id}


def load_state(p: dict[str, Path]) -> tuple[dict[str, Any], bytes]:
    regular_non_symlink(p["ledger"])
    raw = p["ledger"].read_bytes()
    try:
        state = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        fail(f"current ledger is corrupt: {exc}; inspect ledger.prev.json/snapshots read-only")
    validate_ledger(state)
    return state, raw


def load_mutation_state(
    p: dict[str, Path],
    owner_token: str,
    expected_revision: int | None = None,
    *,
    verified: tuple[dict[str, Any], bytes] | None = None,
) -> tuple[dict[str, Any], bytes]:
    """Load or admit a verified publication under owner, revision, and writer fences."""
    state, raw = verified if verified is not None else load_state(p)
    if state["owner"]["token"] != owner_token:
        fail("owner token mismatch; stale orchestrator is fenced")
    if expected_revision is not None and state["revision"] != expected_revision:
        fail(f"revision mismatch: expected {expected_revision}, current {state['revision']}")
    require_mutation_eligible(state)
    return state, raw


def verified_state_file(path: Path, expected_run_id: str) -> tuple[dict[str, Any], bytes] | None:
    """Return only a canonical, schema-valid publication suitable for recovery."""
    try:
        regular_non_symlink(path)
        raw = path.read_bytes()
        state = json.loads(raw.decode("utf-8"))
        validate_ledger(state)
        if state.get("run_id") != expected_run_id or canonical_bytes(state) != raw:
            return None
        return state, raw
    except (LedgerError, OSError, UnicodeError, json.JSONDecodeError):
        return None


def recovery_candidates(p: dict[str, Path], run_id: str) -> list[tuple[dict[str, Any], bytes, Path]]:
    candidates: list[tuple[dict[str, Any], bytes, Path]] = []
    for candidate in (p["prev"],):
        verified = verified_state_file(candidate, run_id)
        if verified:
            candidates.append((*verified, candidate))
    snapshot_root = p["run"] / "snapshots"
    if snapshot_root.exists():
        if snapshot_root.is_symlink() or not snapshot_root.is_dir():
            fail("recovery snapshot namespace is not a regular directory")
        for candidate in snapshot_root.iterdir():
            if candidate.suffix != ".json" or candidate.is_symlink():
                continue
            verified = verified_state_file(candidate, run_id)
            if verified:
                candidates.append((*verified, candidate))
    return sorted(candidates, key=lambda item: (item[0].get("revision", -1), item[2].name), reverse=True)


def snapshot_is_pinned(state: dict[str, Any]) -> bool:
    return (
        any(effect_is_unresolved(op) for op in state.get("operations", []))
        or state.get("lifecycle", {}).get("control") in ("RECOVERING", "ACCEPTED", "FAILED", "CANCELLED")
    )


def snapshot_path(p: dict[str, Path], state: dict[str, Any], kind: str) -> Path:
    snapshot_root = p["run"] / "snapshots"
    safe_kind = re.sub(r"[^A-Za-z0-9._-]+", "-", kind).strip("-") or "checkpoint"
    prefix = "pinned-" if snapshot_is_pinned(state) else ""
    return snapshot_root / f"{prefix}{state['revision']}-{safe_kind}.json"


def write_snapshot(p: dict[str, Path], state: dict[str, Any], kind: str) -> Path:
    snapshot_root = p["run"] / "snapshots"
    regular_directory(p["run"], "run directory")
    if snapshot_root.exists() and (snapshot_root.is_symlink() or not snapshot_root.is_dir()):
        fail("recovery snapshot namespace is not a regular directory")
    snapshot_root.mkdir(parents=True, exist_ok=True)
    target = snapshot_path(p, state, kind)
    raw = canonical_bytes(state)
    if target.exists() or target.is_symlink():
        regular_non_symlink(target)
        if target.read_bytes() != raw:
            fail(f"recovery snapshot destination already exists with different bytes: {target}")
    else:
        atomic_create(target, raw)
    return target


def prune_snapshots(p: dict[str, Path]) -> None:
    snapshot_root = p["run"] / "snapshots"
    if not snapshot_root.exists():
        return
    regular_directory(snapshot_root, "snapshot namespace")
    unpinned = [path for path in snapshot_root.iterdir() if path.suffix == ".json" and not path.name.startswith("pinned-") and not path.is_symlink()]
    unpinned.sort(key=lambda path: (path.stat().st_mtime_ns, path.name), reverse=True)
    for path in unpinned[8:]:
        path.unlink()


def publish(p: dict[str, Path], state: dict[str, Any], previous_raw: bytes | None, snapshot_kind: str | None = None) -> None:
    # Final fence for every publication path, including commands that retain
    # their own lock/publish flow instead of using transaction().
    require_mutation_eligible(state)
    ensure_runtime_provenance(state)
    refresh_control_projection(state)
    validate_ledger(state)
    if previous_raw is not None:
        if not p["prev"].parent.exists():
            fail("ledger parent missing before previous-publication backup")
        atomic_write(p["prev"], previous_raw)
    raw = canonical_bytes(state)
    atomic_write(p["ledger"], raw)
    if snapshot_kind:
        try:
            write_snapshot(p, state, snapshot_kind)
            prune_snapshots(p)
        except (OSError, LedgerError) as exc:
            fail(f"ledger revision {state['revision']} committed; recovery snapshot publication failed: {exc}")


def transaction(
    p: dict[str, Path],
    token: str,
    expected_revision: int | None,
    change: Callable[[dict[str, Any]], None],
    snapshot_kind: str | None = None,
    retry_reconcile: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    with Lock(p["lock"]):
        state, previous_raw = load_state(p)
        if state["owner"]["token"] != token:
            fail("owner token mismatch; stale orchestrator is fenced")
        if expected_revision is not None and state["revision"] != expected_revision:
            if retry_reconcile is not None and state["revision"] == expected_revision + 1:
                # Retry reconciliation is allowed to repair publication
                # artifacts (for example, a missing snapshot), so it is a
                # mutation path and must observe the semantic writer floor.
                require_mutation_eligible(state)
                reconciled = retry_reconcile(state)
                if reconciled is not None:
                    raise IdempotentResult(reconciled)
            fail(f"revision mismatch: expected {expected_revision}, current {state['revision']}")
        state, previous_raw = load_mutation_state(
            p, token, expected_revision, verified=(state, previous_raw)
        )
        next_state = copy.deepcopy(state)
        builder = WritePlanBuilder()
        plan_context = _ACTIVE_WRITE_PLAN.set(builder)
        try:
            change(next_state)
        finally:
            _ACTIVE_WRITE_PLAN.reset(plan_context)
        usage = next_state.setdefault("usage", default_usage())
        usage.setdefault("counters", zero_usage())
        usage.setdefault("trace", [])
        usage.setdefault("shared_setup", zero_usage())
        usage.setdefault("gate_costs", {f"G{i}": zero_usage() for i in range(7)})
        delta = {field: 0 for field in USAGE_FIELDS}
        delta["helper_calls"] = 1
        delta["internal_publications"] = 1
        delta["wall_time_ms"] = max(0, int((time.monotonic() - started) * 1000))
        add_usage(usage["counters"], delta)
        usage["trace"].append({"id": f"trace-{state['revision'] + 1}-helper", "kind": "helper_publication", "actor": "ledger-helper", "subject_ref": state.get("lifecycle", {}).get("next_action", {}).get("kind"), "delta": delta, "evidence_ref": None, "recorded_at": now()})
        next_state["revision"] = state["revision"] + 1
        next_state["previous_publication_hash"] = sha256_bytes(previous_raw)
        next_state["updated_at"] = now()
        ensure_runtime_provenance(next_state)
        refresh_control_projection(next_state)
        # All schema and state invariants run before an immutable artifact is
        # made visible. File-backed references are checked after plan publish.
        validate_ledger(next_state, verify_files=False)
        plan = builder.freeze()
        plan.preflight()
        created = plan.publish()
        try:
            publish(p, next_state, previous_raw, snapshot_kind)
        except (OSError, LedgerError):
            # If the ledger remains at its exact pre-transition bytes, newly
            # created canonical files are unpublished staging. Content-
            # addressed objects remain harmless orphans after this boundary.
            try:
                ledger_raw = p["ledger"].read_bytes()
            except OSError:
                ledger_raw = None
            if ledger_raw == previous_raw:
                for write in reversed(created):
                    if write.kind != "canonical" or not write.destination.exists():
                        continue
                    regular_non_symlink(write.destination)
                    if write.destination.read_bytes() == write.data:
                        write.destination.unlink()
            raise
        return next_state


def object_store(p: dict[str, Path], raw: bytes) -> str:
    digest = sha256_bytes(raw)
    target = p["objects"] / digest
    active_plan = _ACTIVE_WRITE_PLAN.get()
    if active_plan is not None:
        if p["run"].is_symlink() or (p["objects"].exists() and p["objects"].is_symlink()):
            fail("immutable object namespace may not contain symlink directories")
        active_plan.add(target, raw, "object")
        return digest
    if p["run"].is_symlink():
        fail("immutable object run directory may not be a symlink")
    if p["objects"].exists() and (p["objects"].is_symlink() or not p["objects"].is_dir()):
        fail("immutable object namespace is not a regular directory")
    p["objects"].mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        regular_non_symlink(target)
        if sha256_file(target) != digest:
            fail(f"immutable object collision: {target}")
    else:
        atomic_create(target, raw)
    return digest


def canonical_document_path(p: dict[str, Path], document_id: str, document_version: str) -> Path:
    """Resolve one immutable Markdown destination without permitting docs/ escape."""
    safe_id(document_id, "document_id")
    safe_id(document_version, "document_version")
    if p["docs"].exists() and (p["docs"].is_symlink() or not p["docs"].is_dir()):
        fail("canonical document namespace is not a regular directory")
    docs_root = p["docs"].resolve()
    document_dir = p["docs"] / document_id
    destination = document_dir / f"{document_version}.md"
    if document_dir.is_symlink():
        fail("canonical document directory may not be a symlink")
    if document_dir.exists() and not document_dir.is_dir():
        fail("canonical document directory is not a regular directory")
    if destination.is_symlink():
        fail("canonical document destination may not be a symlink")
    if not under(destination.resolve(), docs_root):
        fail("canonical document path escapes the run document namespace")
    return destination


def intent_source_bytes(value: str) -> bytes:
    candidate = Path(value).expanduser()
    if candidate.is_symlink():
        fail("intent source may not be a symlink")
    source = candidate.resolve()
    if not source.exists():
        fail(f"intent source does not exist: {source}")
    regular_non_symlink(source)
    raw = source.read_bytes()
    if len(raw) > 4 * 1024 * 1024:
        fail("intent source exceeds the 4 MiB bound")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(f"intent source must be UTF-8 Markdown: {exc}")
    if not text.strip():
        fail("intent source must contain non-whitespace Markdown")
    return raw


def inbox_file(p: dict[str, Path], attempt_id: str, candidate: Path) -> Path:
    attempt_root = (p["scratch"] / safe_id(attempt_id, "attempt_id")).resolve()
    candidate = candidate.expanduser().absolute()
    if candidate.is_symlink():
        fail("return inbox file must not be a symlink")
    candidate = candidate.parent.resolve() / candidate.name
    if not under(candidate, attempt_root):
        fail("return path escapes the registered exact attempt inbox")
    regular_non_symlink(candidate)
    if candidate.stat().st_size > 4 * 1024 * 1024:
        fail("return exceeds the 4 MiB contract bound")
    return candidate


def attempt_by_id(state: dict[str, Any], attempt_id: str) -> dict[str, Any]:
    for attempt in state.get("attempts", []):
        if attempt["id"] == attempt_id:
            return attempt
    fail(f"unknown attempt: {attempt_id}")


def stable_spawn_request_id(run_id: str, attempt_id: str, epoch: int, packet_hash: str) -> str:
    identity = {"run_id": run_id, "attempt_id": attempt_id, "epoch": epoch, "packet_hash": packet_hash}
    return f"spawn-{sha256_bytes(canonical_bytes(identity))[:24]}"


def initialize_attempt_runtime(run_id: str, attempt: dict[str, Any]) -> None:
    attempt["runtime"] = {
        "spawn_request_id": stable_spawn_request_id(run_id, attempt["id"], attempt["epoch"], attempt["packet_hash"]),
        "liveness": "unknown", "runtime_instance_id": None, "start_ref": None, "stop_ref": None,
        "not_started_ref": None, "return_observation_ref": None, "heartbeat_refs": [], "observation_refs": [],
    }


def runtime_liveness(attempt: dict[str, Any]) -> str:
    runtime = attempt.get("runtime")
    return runtime.get("liveness", "unknown") if isinstance(runtime, dict) else "unknown"


def runtime_stop_proven(p: dict[str, Path], attempt: dict[str, Any]) -> bool:
    """Validate an exact typed stop/not-started receipt; legacy attempts stay unknown."""
    runtime = attempt.get("runtime")
    if not isinstance(runtime, dict):
        return True
    if runtime.get("liveness") == "not_started":
        ref = runtime.get("not_started_ref")
        expected_event = "not_started"
    elif runtime.get("liveness") == "stopped":
        ref = runtime.get("stop_ref")
        expected_event = "stop"
    else:
        return False
    if not isinstance(ref, str):
        return False
    if ref not in runtime.get("observation_refs", []):
        return False
    observation = stored_payload(p, ref, "runtime stop observation")
    root = schema()
    validate(observation, root["$defs"]["runtime_observation"], root, "$.runtime_observation")
    return bool(
        observation.get("kind") == "runtime_observation"
        and observation.get("event") == expected_event
        and observation.get("run_id") == p["run"].name
        and observation.get("attempt_id") == attempt.get("id")
        and observation.get("epoch") == attempt.get("epoch")
        and observation.get("packet_hash") == attempt.get("packet_hash")
        and observation.get("spawn_request_id") == runtime.get("spawn_request_id")
        and observation.get("runtime_instance_id") == runtime.get("runtime_instance_id")
        and (expected_event != "stop" or observation.get("coverage", {}).get("descendant_writers") == "included")
    )


def require_runtime_stopped(p: dict[str, Path], attempt: dict[str, Any], action: str) -> None:
    if isinstance(attempt.get("runtime"), dict) and not runtime_stop_proven(p, attempt):
        fail(f"{action} requires an exact runtime stop/not_started observation; liveness={runtime_liveness(attempt)}")


def packet_identity(packet: dict[str, Any]) -> dict[str, Any]:
    identity = packet.get("identity")
    if not isinstance(identity, dict):
        fail("packet/return identity is required")
    return identity


def validate_route_eligibility(route: dict[str, Any]) -> None:
    if route.get("adequacy") != "CONFIRMED":
        fail(f"route is not eligible for dispatch: adequacy={route.get('adequacy')}")
    context_grade = route.get("context_grade")
    if not isinstance(context_grade, str) or context_grade not in VALID_CONTEXT_GRADES:
        fail(f"route is not eligible for dispatch: invalid context_grade={context_grade!r}")
    fallback = route.get("fallback_cause")
    if fallback is not None:
        if fallback not in CAUSES:
            fail(f"route is not eligible for dispatch: invalid fallback_cause={fallback!r}")
        if not route.get("requested_binding") and not route.get("observed_binding"):
            fail("route is not eligible for dispatch: fallback lacks requested/observed binding")
        if context_grade in {"UNKNOWN", "REJECTED"}:
            fail("route is not eligible for dispatch: fallback context is not usable")


def nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        fail(f"{label} must be a non-empty string")
    return value


def ids_from_records(records: list[dict[str, Any]], key: str, label: str) -> list[str]:
    values: list[str] = []
    for record in records:
        value = record.get(key)
        safe_id(value, label)
        values.append(value)
    if len(values) != len(set(values)):
        fail(f"duplicate {label} records")
    return values


def design_bundle_source(record: dict[str, Any]) -> tuple[Path, bytes]:
    source_value = record.get("source")
    if not isinstance(source_value, str) or not source_value or not Path(source_value).is_absolute() or ".." in Path(source_value).parts:
        fail("design artifact source must be an absolute, traversal-free path")
    candidate = Path(source_value).expanduser()
    if candidate.is_symlink():
        fail("design artifact source may not be a symlink")
    source = candidate.resolve()
    if not source.exists():
        fail(f"design artifact source does not exist: {source}")
    regular_non_symlink(source)
    if source.stat().st_size > 4 * 1024 * 1024:
        fail("design artifact exceeds the 4 MiB bound")
    raw = source.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(f"design artifact must be UTF-8 Markdown: {exc}")
    if not text.strip():
        fail("design artifact must contain non-whitespace Markdown")
    if sha256_bytes(raw) != record.get("hash"):
        fail(f"design artifact hash does not match source: {record.get('id')}")
    return source, raw


def validate_design_bundle(bundle: dict[str, Any]) -> None:
    """Validate the complete proposed design publication without touching state."""
    safe_id(bundle.get("bundle_id"), "design bundle ID")
    root = schema()
    documents = bundle.get("documents", [])
    document_ids = ids_from_records(documents, "id", "design document")
    kinds = {item.get("kind") for item in documents}
    if "design" not in kinds:
        fail("design bundle requires a design artifact")
    if not ({"interfaces", "contracts", "interface"} & kinds) or not bundle.get("contracts"):
        fail("design bundle requires interfaces and contract records")
    if "manifest" not in kinds:
        fail("design bundle requires a manifest artifact")
    if not ({"plan", "implementation_plan", "implementation-plan", "evaluation_plan", "evaluation-plan"} & kinds):
        fail("design bundle requires an implementation plan artifact")
    if not ({"tickets", "implementation_tickets", "implementation-tickets"} & kinds) or not bundle.get("tickets"):
        fail("design bundle requires a tickets artifact and ticket records")
    if not ({"routes", "route", "dependencies"} & kinds) or not bundle.get("routes"):
        fail("design bundle requires routes/dependencies and route records")
    for document in documents:
        design_bundle_source(document)
    for name in ("contracts", "tickets", "routes"):
        definition = root["$defs"][name[:-1] if name != "routes" else "route"]
        for index, record in enumerate(bundle[name]):
            validate(record, definition, root, f"$.{name}[{index}]")
            safe_id(record["id"], f"{name[:-1]} ID")
    all_bundle_ids = document_ids + [item["id"] for item in bundle["contracts"]] + [item["id"] for item in bundle["tickets"]] + [item["id"] for item in bundle["routes"]]
    if len(all_bundle_ids) != len(set(all_bundle_ids)):
        fail("design bundle contains duplicate immutable IDs")
    for route in bundle["routes"]:
        validate_route_eligibility(route)
    validate_ticket_contract_bindings(bundle["contracts"], bundle["tickets"], "design bundle")
    ticket_ids = {item["id"] for item in bundle["tickets"]}
    graph = {item["id"]: set(item.get("dependency_refs", [])) for item in bundle["tickets"]}
    if any(ref not in ticket_ids for refs in graph.values() for ref in refs):
        fail("design bundle ticket dependency references a ticket outside the bundle")
    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(ticket_id: str) -> None:
        if ticket_id in visiting:
            fail("design bundle ticket dependency graph contains a cycle")
        if ticket_id in visited:
            return
        visiting.add(ticket_id)
        for dependency_id in graph[ticket_id]:
            visit(dependency_id)
        visiting.remove(ticket_id)
        visited.add(ticket_id)
    for ticket_id in graph:
        visit(ticket_id)

    def depends(ticket_id: str, dependency_id: str, seen: set[str] | None = None) -> bool:
        seen = set() if seen is None else seen
        if ticket_id in seen:
            fail("design bundle ticket dependency graph contains a cycle")
        seen.add(ticket_id)
        if dependency_id in graph[ticket_id]:
            return True
        return any(depends(item, dependency_id, set(seen)) for item in graph[ticket_id])

    def zones_overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
        for left_zone in left.get("zone", []):
            left_path = relative_path(left_zone.get("path"), "ticket zone").rstrip("/")
            for right_zone in right.get("zone", []):
                right_path = relative_path(right_zone.get("path"), "ticket zone").rstrip("/")
                if left_path == right_path or left_path.startswith(right_path + "/") or right_path.startswith(left_path + "/"):
                    return True
        return False

    for index, left in enumerate(bundle["tickets"]):
        for right in bundle["tickets"][index + 1:]:
            if zones_overlap(left, right) and not depends(left["id"], right["id"]) and not depends(right["id"], left["id"]):
                fail(f"ticket zones overlap without dependency ordering: {left['id']} / {right['id']}")


def _binding_normalization_for_pair(
    state: dict[str, Any], ticket_ref: str, contract_ref: str,
    publication_ref: str | None = None, publication_hash: str | None = None,
) -> dict[str, Any] | None:
    """Return an exact current-publication normalization for one raw self-input pair."""
    publication = state.get("design_publication") or {}
    expected_ref = publication_ref or publication.get("id")
    expected_hash = publication_hash or publication.get("publication_hash")
    matches = []
    for event in state.get("binding_normalizations", []):
        if event.get("publication_ref") != expected_ref or event.get("publication_hash") != expected_hash:
            continue
        for item in event.get("bindings", []):
            if item.get("ticket_ref") == ticket_ref and item.get("contract_ref") == contract_ref:
                matches.append(item)
    if len(matches) > 1:
        fail(f"overlapping effective binding normalizations for {ticket_ref} / {contract_ref}")
    return matches[0] if matches else None


def effective_ticket_contract_bindings(
    state: dict[str, Any], ticket: dict[str, Any],
) -> dict[str, list[str]]:
    """Project immutable raw contract refs into executable inputs and specification refs."""
    executable: list[str] = []
    specification: list[str] = []
    ticket_id = ticket.get("id")
    for ref in ticket.get("contract_refs", []):
        contract = next((item for item in state.get("contracts", []) if item.get("id") == ref), None)
        self_input = contract is not None and ticket_id in contract.get("producer_refs", [])
        normalization = (
            _binding_normalization_for_pair(state, ticket_id, ref)
            if self_input and ticket_id else None
        )
        if (
            normalization
            and normalization.get("classification") == "metadata_only"
            and normalization.get("effective_role") == "specification_only"
            and normalization.get("original_relation") == "self_input"
            and normalization.get("implementation_availability") == "not_required"
            and normalization.get("equivalence_refs")
            and normalization.get("evidence_refs")
        ):
            specification.append(ref)
        else:
            executable.append(ref)
    return {"implementation_input_refs": executable, "specification_refs": specification}


def validate_ticket_contract_bindings(
    contracts: list[dict[str, Any]], tickets: list[dict[str, Any]], label: str,
    *, state: dict[str, Any] | None = None,
) -> None:
    """Keep ticket inputs distinct from contracts produced by that ticket.

    ``ticket.contract_refs`` has always fed readiness and is therefore an
    input list.  ``contract.producer_refs`` is the existing output binding.
    Rejecting their intersection avoids silently reinterpreting legacy mixed
    bundles or activating a proposed output.
    """
    contract_by_id = {item.get("id"): item for item in contracts}
    for ticket in tickets:
        ticket_id = ticket.get("id")
        effective_refs = (
            effective_ticket_contract_bindings(state, ticket)["implementation_input_refs"]
            if state is not None else ticket.get("contract_refs", [])
        )
        for contract_ref in effective_refs:
            contract = contract_by_id.get(contract_ref)
            if contract is None:
                continue
            if ticket_id in contract.get("producer_refs", []):
                fail(
                    f"{label} ticket {ticket_id} requires self-produced contract {contract_ref} as an input; "
                    "remove it from ticket.contract_refs and retain the explicit contract.producer_refs output binding"
                )


def validate_current_design_contract_bindings(state: dict[str, Any]) -> None:
    """Apply the input/output guard to an already-published legacy bundle."""
    publication = current_design_publication(state)
    ticket_refs = set(publication.get("ticket_refs", []))
    tickets = [item for item in state.get("tickets", []) if item.get("id") in ticket_refs]
    validate_ticket_contract_bindings(
        state.get("contracts", []), tickets, "current design publication", state=state,
    )


def _contract_has_integrated_producer(state: dict[str, Any], contract: dict[str, Any]) -> bool:
    """Treat implementation as available only with explicit evidence or a current integrated producer."""
    tickets = {item.get("id"): item for item in state.get("tickets", [])}
    candidates = {item.get("id"): item for item in state.get("candidates", [])}
    for producer_ref in contract.get("producer_refs", []):
        producer = tickets.get(producer_ref)
        candidate = candidates.get(producer.get("current_candidate")) if producer else None
        if (
            producer and producer.get("state") == "INTEGRATED"
            and candidate and candidate.get("quality") == "DONE"
            and candidate.get("integration_status") == "INTEGRATED"
            and not candidate.get("invalidated_by")
        ):
            return True
    return False


def validate_ticket_implementation_availability(
    state: dict[str, Any], tickets: list[dict[str, Any]], label: str,
    *, allow_planned_producers: bool = False,
) -> None:
    """Fail closed when executable inputs have no availability evidence or producer path."""
    publication = state.get("design_publication") or {}
    publication_tickets = {
        item.get("id"): item for item in state.get("tickets", [])
        if item.get("id") in set(publication.get("ticket_refs", []))
    }

    def depends_on(ticket_id: str, producer_id: str, visiting: set[str] | None = None) -> bool:
        visiting = set() if visiting is None else visiting
        if ticket_id in visiting:
            return False
        visiting.add(ticket_id)
        ticket = publication_tickets.get(ticket_id)
        if ticket is None:
            return False
        dependencies = ticket.get("dependency_refs", [])
        return producer_id in dependencies or any(depends_on(dep, producer_id, set(visiting)) for dep in dependencies)

    contracts = {item.get("id"): item for item in state.get("contracts", [])}
    for ticket in tickets:
        effective = effective_ticket_contract_bindings(state, ticket)
        for ref in effective["implementation_input_refs"]:
            contract = contracts.get(ref)
            if contract is None or contract.get("status") != "active" or contract.get("invalidated_by"):
                fail(f"{label} ticket {ticket.get('id')} has no current accepted contract input: {ref}")
            availability = contract.get("implementation_availability", "unknown")
            evidence = contract.get("implementation_availability_evidence_refs", [])
            if availability == "available" and evidence:
                continue
            if availability == "unavailable":
                fail(f"{label} ticket {ticket.get('id')} requires unavailable implementation input: {ref}")
            if availability == "not_required":
                fail(f"{label} ticket {ticket.get('id')} marks executable input as not_required: {ref}")
            if _contract_has_integrated_producer(state, contract):
                continue
            if allow_planned_producers:
                producers = [
                    producer_ref for producer_ref in contract.get("producer_refs", [])
                    if producer_ref in publication_tickets and producer_ref != ticket.get("id")
                    and depends_on(ticket.get("id"), producer_ref)
                ]
                if producers:
                    continue
            fail(
                f"{label} ticket {ticket.get('id')} requires implementation availability evidence or an "
                f"current integrated producer for contract {ref} (status alone is insufficient)"
            )


def validate_effective_ticket_contract_bindings(
    state: dict[str, Any], tickets: list[dict[str, Any]], label: str,
    *, require_availability: bool = False, allow_planned_producers: bool = False,
) -> None:
    validate_ticket_contract_bindings(state.get("contracts", []), tickets, label, state=state)
    contracts = {item.get("id"): item for item in state.get("contracts", [])}
    for ticket in tickets:
        for ref in effective_ticket_contract_bindings(state, ticket)["specification_refs"]:
            contract = contracts.get(ref)
            if contract is None or contract.get("status") != "active" or contract.get("invalidated_by"):
                fail(f"{label} ticket {ticket.get('id')} has no current accepted specification binding: {ref}")
    if require_availability:
        validate_ticket_implementation_availability(
            state, tickets, label, allow_planned_producers=allow_planned_producers,
        )


def _read_manifest(path_value: str | Path, label: str) -> tuple[dict[str, Any], bytes]:
    path = Path(path_value).expanduser()
    regular_non_symlink(path)
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        fail(f"{label} is not valid UTF-8 JSON: {exc}")
    if not isinstance(value, dict):
        fail(f"{label} must be a JSON object")
    return value, raw


def legacy_contract_intersections(state: dict[str, Any]) -> list[dict[str, str]]:
    """Enumerate every current-publication input/output self-intersection deterministically."""
    publication = state.get("design_publication") or {}
    tickets = {item.get("id"): item for item in state.get("tickets", [])}
    contracts = {item.get("id"): item for item in state.get("contracts", [])}
    pairs: list[dict[str, str]] = []
    for ticket_ref in publication.get("ticket_refs", []):
        ticket = tickets.get(ticket_ref)
        if ticket is None:
            continue
        for contract_ref in publication.get("contract_refs", []):
            contract = contracts.get(contract_ref)
            if contract is not None and contract_ref in ticket.get("contract_refs", []) and ticket_ref in contract.get("producer_refs", []):
                pairs.append({"ticket_ref": ticket_ref, "contract_ref": contract_ref})
    return sorted(pairs, key=lambda item: (item["ticket_ref"], item["contract_ref"]))


def assess_legacy_binding_manifest(
    state: dict[str, Any], source_raw: bytes, manifest: dict[str, Any],
) -> dict[str, Any]:
    """Validate a frozen source binding inventory and return its classifications without mutation."""
    root = schema()
    validate(manifest, root["$defs"]["binding_normalization_manifest"], root, "$.binding_manifest")
    publication = state.get("design_publication") or {}
    source_hash = sha256_bytes(source_raw)
    checks = {
        "source_revision": (manifest.get("source_revision"), state.get("revision")),
        "source_ledger_hash": (manifest.get("source_ledger_hash"), source_hash),
        "owner_epoch": (manifest.get("owner_epoch"), (state.get("owner") or {}).get("epoch")),
        "publication_ref": (manifest.get("publication_ref"), publication.get("id")),
        "publication_hash": (manifest.get("publication_hash"), publication.get("publication_hash")),
    }
    for name, (supplied, expected) in checks.items():
        if supplied != expected:
            fail(f"binding manifest {name} does not match exact source state")

    pairs = legacy_contract_intersections(state)
    supplied_items = manifest.get("bindings", [])
    supplied_pairs = [
        (item.get("ticket_ref"), item.get("contract_ref")) for item in supplied_items
    ]
    expected_pairs = [(item["ticket_ref"], item["contract_ref"]) for item in pairs]
    if len(supplied_pairs) != len(set(supplied_pairs)) or sorted(supplied_pairs) != expected_pairs:
        fail("binding manifest must classify every current self-input intersection exactly once")

    classified: list[dict[str, Any]] = []
    for item in sorted(supplied_items, key=lambda row: (row["ticket_ref"], row["contract_ref"])):
        if item.get("original_relation") != "self_input":
            fail("binding manifest original_relation must preserve the exact self_input relation")
        if item.get("original_refs") != [item["ticket_ref"], item["contract_ref"]]:
            fail("binding manifest original_refs must be the exact [ticket_ref, contract_ref] pair")
        if not item.get("evidence_refs") or not item.get("equivalence_refs"):
            fail("binding classifications require exact evidence_refs and equivalence_refs")
        row = copy.deepcopy(item)
        if row.get("classification") == "metadata_only":
            if row.get("effective_role") == "specification_only":
                if row.get("implementation_availability") != "not_required":
                    fail("specification_only normalization must declare implementation_availability=not_required")
                if not row.get("implementation_availability_evidence_refs"):
                    fail("specification_only normalization requires availability evidence refs")
            elif row.get("implementation_availability") != "available":
                fail("implementation_input normalization requires explicit available implementation evidence")
        classified.append(row)
    counts = {
        classification: sum(1 for item in classified if item.get("classification") == classification)
        for classification in ("metadata_only", "material_change", "ambiguous")
    }
    return {
        "valid": True,
        "migration_eligible": bool(classified) and counts["metadata_only"] == len(classified)
        and all(item.get("effective_role") == "specification_only" for item in classified),
        "source_revision": state["revision"],
        "source_ledger_hash": source_hash,
        "publication_ref": publication.get("id"),
        "publication_hash": publication.get("publication_hash"),
        "intersection_count": len(pairs),
        "distinct_ticket_count": len({item["ticket_ref"] for item in pairs}),
        "metadata_only_count": counts["metadata_only"],
        "material_change_count": counts["material_change"],
        "ambiguous_count": counts["ambiguous"],
        "intersections": classified,
    }


def _cmd_assess_legacy_bindings(args: argparse.Namespace) -> dict[str, Any]:
    """Read-only compatibility assessment against exact standalone ledger bytes."""
    source_file = Path(args.file).expanduser()
    regular_non_symlink(source_file)
    source_raw = source_file.read_bytes()
    try:
        state = json.loads(source_raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        fail(f"legacy source ledger is not valid UTF-8 JSON: {exc}")
    if not isinstance(state, dict):
        fail("legacy source ledger must be a JSON object")
    validate_ledger(state, verify_files=False)
    manifest, manifest_raw = _read_manifest(args.manifest, "binding normalization manifest")
    assessment = assess_legacy_binding_manifest(state, source_raw, manifest)
    return {
        **assessment,
        "read_only": True,
        "manifest_hash": sha256_bytes(manifest_raw),
    }


def _bootstrap_legacy_candidate_model(p: dict[str, Path], state: dict[str, Any]) -> None:
    """Conservatively bootstrap only R58's exact continuation candidate from its immutable receipt."""
    if state.get("candidate_model_version") == "1.1":
        return
    if state.get("candidates") or any(ticket.get("current_candidate") for ticket in state.get("tickets", [])):
        fail("legacy candidate bootstrap is ambiguous: candidate records or pointers already exist")
    ticket = next((item for item in state.get("tickets", []) if item.get("id") == "T02-R17"), None)
    if ticket is None or ticket.get("state") != "BLOCKED":
        fail("legacy candidate bootstrap requires the exact blocked T02-R17 ticket")
    worker = next((item for item in state.get("attempts", []) if item.get("id") == "T02-R17-WORKER-05"), None)
    if (
        worker is None or worker.get("kind") != "worker" or worker.get("subject_ref") != ticket["id"]
        or worker.get("state") != "RETURNED" or ticket.get("current_attempt") != worker.get("id")
        or not worker.get("candidate_sha") or not worker.get("candidate_tree_sha")
        or not worker.get("continuation_ref")
    ):
        fail("legacy candidate bootstrap lacks the exact current returned Worker05 candidate identity")
    receipt = stored_payload(p, worker.get("continuation_ref"), "Worker05 continuation receipt")
    expected = {
        "attempt_id": worker["id"], "candidate_sha": worker["candidate_sha"],
        "candidate_tree_sha": worker["candidate_tree_sha"], "base_sha": worker.get("base_sha"),
        "authorization_ref": worker.get("continuation_authorization_ref"),
    }
    if any(receipt.get(key) != value for key, value in expected.items()):
        fail("Worker05 continuation receipt does not match the exact ledger candidate identity")
    blocker_ref = receipt.get("blocker_ref")
    blocker = next((item for item in state.get("issues", []) if item.get("id") == blocker_ref), None)
    if receipt.get("blocker_scope") != "external" or blocker is None or blocker.get("invalidated_by"):
        fail("Worker05 continuation bootstrap requires its exact still-current external blocker")
    candidate_id = f"candidate-{worker['id']}"
    if any(item.get("id") == candidate_id for item in state.get("candidates", [])):
        fail("legacy candidate bootstrap collides with an existing candidate ID")
    state.setdefault("candidates", []).append({
        "id": candidate_id, "ticket_ref": ticket["id"], "sha": worker["candidate_sha"],
        "tree_sha": worker["candidate_tree_sha"], "base_sha": worker.get("base_sha"),
        "producer_attempt_ref": worker["id"], "parent_candidate_ref": None,
        "quality": "CONTINUATION", "blocker_refs": [blocker_ref],
        "review_status": "BLOCK", "integration_status": "PENDING",
        "proof_ref": None,
    })
    attempts_by_id = {item.get("id"): item for item in state.get("attempts", [])}
    for item in state.get("tickets", []):
        item["current_candidate"] = None
        prior = attempts_by_id.get(item.get("current_attempt"))
        workers = [
            attempt for attempt in state.get("attempts", [])
            if attempt.get("kind") == "worker" and attempt.get("subject_ref") == item.get("id")
        ]
        last_worker = prior if prior and prior.get("kind") == "worker" else (
            max(workers, key=lambda attempt: attempt.get("attempt_created_revision", -1)) if workers else None
        )
        item["last_worker_attempt"] = last_worker.get("id") if last_worker else None
        item["current_attempt"] = item["last_worker_attempt"]
        item["current_worker_attempt"] = (
            item["last_worker_attempt"]
            if last_worker and last_worker.get("state") in ("PREPARED", "DISPATCHED") else None
        )
    ticket["current_candidate"] = candidate_id
    state["candidate_model_version"] = "1.1"
    state["review_model_version"] = "1.1"
    state.setdefault("review_qualifications", [])
    state.setdefault("repair_waves", [])
    state.setdefault("acceptance", [])


def _locked_migration_load(p: dict[str, Path], owner_token: str) -> tuple[dict[str, Any], bytes]:
    """Load a mutation source under owner/revision fences, allowing explicit legacy migration only."""
    state, raw = load_state(p)
    if state.get("owner", {}).get("token") != owner_token:
        fail("owner token mismatch; stale orchestrator is fenced")
    return state, raw


def _cmd_migrate_legacy_bindings(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    manifest, manifest_raw = _read_manifest(args.manifest, "binding normalization manifest")
    manifest_hash = sha256_bytes(manifest_raw)
    root = schema()
    validate(manifest, root["$defs"]["binding_normalization_manifest"], root, "$.binding_manifest")
    with Lock(p["lock"]):
        state, previous_raw = _locked_migration_load(p, args.owner_token)
        prior = next((item for item in state.get("binding_normalizations", []) if item.get("migration_id") == manifest["migration_id"]), None)
        if prior is not None:
            if prior.get("manifest_hash") == manifest_hash and prior.get("source_ledger_hash") == manifest.get("source_ledger_hash") and prior.get("source_revision") == manifest.get("source_revision"):
                if args.revision not in {manifest.get("source_revision"), prior.get("applied_revision"), state.get("revision")}:
                    fail(f"revision mismatch on migration replay: expected source/applied/current revision, got {args.revision}")
                return {"migrated": True, "idempotent": True, "migration_id": manifest["migration_id"], "manifest_hash": manifest_hash, "applied_revision": prior.get("applied_revision"), "normalized_binding_count": len(prior.get("bindings", []))}
            fail("binding migration ID already exists with conflicting manifest/source")
        if state.get("revision") != args.revision:
            fail(f"revision mismatch: expected {args.revision}, current {state.get('revision')}")
        assessment = assess_legacy_binding_manifest(state, previous_raw, manifest)
        if not assessment["migration_eligible"]:
            fail("binding migration rejected: every intersection must be exact metadata_only specification_only with equivalence evidence")
        if state.get("owner", {}).get("epoch") != manifest.get("owner_epoch"):
            fail("binding manifest owner_epoch does not match current owner epoch")
        _bootstrap_legacy_candidate_model(p, state)
        manifest_ref = object_store(p, manifest_raw)
        migration_id = manifest["migration_id"]
        event_id = f"binding-normalization-{migration_id}"
        if any(item.get("id") == event_id for item in state.get("binding_normalizations", [])):
            fail("binding normalization event ID already exists")
        applied_revision = state["revision"] + 1
        bindings = []
        for item in assessment["intersections"]:
            normalized = copy.deepcopy(item)
            normalized["implementation_availability"] = "not_required"
            bindings.append(normalized)
        state.setdefault("binding_normalizations", []).append({
            "id": event_id, "migration_id": migration_id,
            "source_revision": assessment["source_revision"],
            "source_ledger_hash": assessment["source_ledger_hash"],
            "publication_ref": assessment["publication_ref"],
            "publication_hash": assessment["publication_hash"],
            "manifest_hash": manifest_hash, "manifest_ref": f"objects/{manifest_ref}",
            "owner_epoch": manifest["owner_epoch"], "applied_revision": applied_revision,
            "bindings": bindings, "recorded_at": now(),
        })
        provenance = ensure_runtime_provenance(state)
        provenance["state_contract_version"] = STATE_CONTRACT_VERSION
        provenance["minimum_writer_version"] = WRITER_VERSION
        provenance["applied_migrations"].append({
            "id": f"legacy-bindings-{migration_id}", "helper_version": SKILL_VERSION,
            "applied_revision": applied_revision, "manifest_hash": manifest_hash,
            "object_ref": f"objects/{manifest_ref}",
        })
        state["revision"] = applied_revision
        state["previous_publication_hash"] = sha256_bytes(previous_raw)
        state["updated_at"] = now()
        validate_ledger(state, verify_files=False)
        publish(p, state, previous_raw, "legacy-binding-normalization")
        return {"migrated": True, "idempotent": False, "migration_id": migration_id, "manifest_hash": manifest_hash, "applied_revision": applied_revision, "normalized_binding_count": len(bindings)}


def stored_payload(p: dict[str, Path], ref: str | None, label: str) -> dict[str, Any]:
    match = re.fullmatch(r"objects/([0-9a-f]{64})", ref) if isinstance(ref, str) else None
    if match is None:
        fail(f"{label} is not an immutable object reference")
    run_fd = objects_fd = object_fd = None
    try:
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        run_fd = os.open(p["run"], directory_flags)
        if not stat.S_ISDIR(os.fstat(run_fd).st_mode):
            fail(f"{label} run namespace is not a regular directory")
        objects_fd = os.open("objects", directory_flags, dir_fd=run_fd)
        if not stat.S_ISDIR(os.fstat(objects_fd).st_mode):
            fail(f"{label} immutable object namespace is not a regular directory")
        object_fd = os.open(match.group(1), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=objects_fd)
        if not stat.S_ISREG(os.fstat(object_fd).st_mode):
            fail(f"{label} immutable object is not a regular file")
        with os.fdopen(object_fd, "rb") as stream:
            object_fd = None
            raw = stream.read()
    except OSError as exc:
        fail(f"{label} immutable object is unavailable: {exc}")
    finally:
        for descriptor in (object_fd, objects_fd, run_fd):
            if descriptor is not None:
                os.close(descriptor)
    if sha256_bytes(raw) != match.group(1):
        fail(f"{label} immutable object hash does not match its reference")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        fail(f"invalid {label} immutable object objects/{match.group(1)}: {exc}")
    if not isinstance(value, dict):
        fail(f"{label} immutable object must contain a JSON object")
    return value


def validate_worker_return_semantics(payload: dict[str, Any], packet: dict[str, Any]) -> None:
    acceptance = packet.get("acceptance", [])
    checks = packet.get("verification", [])
    criteria = payload.get("criteria", [])
    returned_criteria = ids_from_records(criteria, "criterion_id", "worker criterion")
    required_criteria = ids_from_records(acceptance, "criterion_id", "packet criterion")
    if set(returned_criteria) != set(required_criteria):
        fail("worker return criteria do not correspond exactly to the packet")
    check_records = payload.get("checks", [])
    returned_checks = ids_from_records(check_records, "check_id", "worker check")
    required_checks = ids_from_records([item for item in checks if item.get("required", True)], "check_id", "packet check")
    if not set(required_checks).issubset(returned_checks):
        fail("worker return omits required packet checks")
    if payload.get("status") == "DONE" and any(record.get("outcome") != "pass" for record in check_records if record.get("check_id") in required_checks):
        fail("worker return has a failed or non-passing required check")
    if payload.get("status") == "DONE" and any(record.get("outcome") != "satisfied" for record in criteria):
        fail("worker return has an unsatisfied or unverifiable criterion")
    for record in payload.get("files", []):
        relative_path(record.get("path"), "worker file path")
        if record.get("operation") == "rename":
            relative_path(record.get("from"), "worker rename source")
            relative_path(record.get("to"), "worker rename target")
    issues = payload.get("issues", [])
    if payload.get("status") == "DONE" and any(item.get("impact") == "blocking" for item in issues):
        fail("DONE worker return contains a blocking issue")
    if payload.get("status") == "DONE" and (not required_criteria or not required_checks):
        fail("DONE worker return is not semantically complete")
    if payload.get("status") in ("BLOCKED", "FAILED") and not payload.get("issues"):
        fail(f"{payload['status']} worker return requires a typed issue")
    if payload.get("status") == "HANDOFF" and not payload.get("handoff"):
        fail("HANDOFF worker return requires a handoff object")


def worker_return_write_set_violations(payload: dict[str, Any], lease: dict[str, Any]) -> list[dict[str, str]]:
    """Return worker-declared paths/operations that exceed the current lease."""
    zone = lease.get("zone", [])

    def allowed(path: str, operation: str) -> bool:
        for entry in zone:
            zone_path = relative_path(entry.get("path"), "lease zone path").rstrip("/")
            if (path == zone_path or path.startswith(zone_path + "/")) and operation in entry.get("operations", []):
                return True
        return False

    violations: list[dict[str, str]] = []
    for record in payload.get("files", []):
        operation = record.get("operation")
        paths = [(record.get("path"), operation)]
        if operation == "rename":
            paths.extend(((record.get("from"), operation), (record.get("to"), operation)))
        for value, claimed_operation in paths:
            if value is None:
                continue
            path = relative_path(value, "worker file path")
            if not allowed(path, claimed_operation):
                violations.append({"path": path, "operation": claimed_operation})
    return violations


def zone_allows(zone: list[dict[str, Any]], path: str, operation: str) -> bool:
    clean = relative_path(path, "write allow path")
    for entry in zone:
        zone_path = relative_path(entry.get("path"), "ticket zone path").rstrip("/")
        if (clean == zone_path or clean.startswith(zone_path + "/")) and operation in entry.get("operations", []):
            return True
    return False


def packet_write_zone(packet: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize the packet allowlist into the exact effective lease shape."""
    merged: dict[str, set[str]] = {}
    for entry in packet.get("write", {}).get("allow", []):
        path = relative_path(entry.get("path"), "packet write allow path").rstrip("/")
        merged.setdefault(path, set()).update(entry.get("operations", []))
    return [{"path": path, "operations": sorted(operations)} for path, operations in sorted(merged.items())]


def validate_execution_binding(
    p: dict[str, Path], state: dict[str, Any], ticket: dict[str, Any], packet: dict[str, Any], *,
    kind: str, attempt_id: str, packet_hash: str, route_id: str,
    route: dict[str, Any] | None = None, attempt: dict[str, Any] | None = None,
    return_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate and derive the one authoritative binding for a worker attempt.

    New worker dispatches and their returns share this projection. Historical
    attempts remain readable because the execution-binding fields are optional
    in the ledger schema, but a new dispatch cannot omit any current authority.
    """
    if kind != "worker" or packet.get("kind") != kind:
        fail("execution binding kind does not match the registered worker packet")
    if packet.get("mode") not in ("implement", "repair"):
        fail("execution binding requires an implement or repair worker packet")
    identity = packet_identity(packet)
    if (
        identity.get("run_id") != state.get("run_id")
        or identity.get("ticket_id") != ticket.get("id")
        or identity.get("attempt_id") != attempt_id
    ):
        fail("execution binding must name the exact current run, ticket, and attempt")
    epoch = state.get("owner", {}).get("epoch")
    if identity.get("epoch") != epoch:
        fail("execution binding epoch does not match the current owner")

    publication = current_design_publication(state)
    if ticket.get("id") not in publication.get("ticket_refs", []):
        fail("execution binding ticket is not part of the current design publication")
    intent = current_intent_binding(state)
    publication_intent = (
        publication.get("intent_revision"), publication.get("intent_document_ref"),
        publication.get("intent_document_hash"),
    )
    if publication_intent != (intent["revision"], intent["document_ref"], intent["document_hash"]):
        fail("execution binding design publication is not bound to the current intent")
    expected_publication = {
        "design_publication_ref": publication.get("id"),
        "design_publication_hash": publication.get("publication_hash"),
        "design_publication_revision": publication.get("published_revision"),
    }
    expected_intent = {
        "intent_revision": intent["revision"],
        "intent_document_ref": intent["document_ref"],
        "intent_document_hash": intent["document_hash"],
    }
    for field, expected in {**expected_publication, **expected_intent}.items():
        if identity.get(field) != expected:
            fail(f"execution binding identity {field} is missing or stale")
    for field, expected in expected_intent.items():
        if packet.get(field) != expected:
            fail(f"worker packet {field} is missing or stale")

    ticket_criteria = ticket.get("criterion_refs", [])
    active_criteria = {
        item.get("id") for item in state.get("criteria", [])
        if item.get("status") == "active" and not item.get("invalidated_by")
    }
    if (
        not ticket_criteria or len(ticket_criteria) != len(set(ticket_criteria))
        or not set(ticket_criteria).issubset(active_criteria)
    ):
        fail("execution binding requires a non-empty current authoritative ticket criterion set")
    if not set(ticket_criteria).issubset(set(publication.get("criterion_refs", []))):
        fail("current design publication does not cover the full authoritative ticket criteria")
    packet_criteria = [item.get("criterion_id") for item in packet.get("acceptance", [])]
    if len(packet_criteria) != len(set(packet_criteria)) or set(packet_criteria) != set(ticket_criteria):
        fail("worker packet acceptance must cover the full authoritative ticket criteria")

    contract_refs = ticket.get("contract_refs", [])
    if len(contract_refs) != len(set(contract_refs)):
        fail("execution binding ticket contract refs must be unique")
    if not set(contract_refs).issubset(set(publication.get("contract_refs", []))):
        fail("current design publication does not cover the full authoritative ticket contracts")
    supplied_contract_refs = identity.get("contract_refs")
    if not isinstance(supplied_contract_refs, list) or len(supplied_contract_refs) != len(set(supplied_contract_refs)) or set(supplied_contract_refs) != set(contract_refs):
        fail("worker packet contract_refs must exactly cover the authoritative ticket contracts")
    validate_effective_ticket_contract_bindings(
        state, [ticket], "worker execution binding", require_availability=True,
    )
    effective = effective_ticket_contract_bindings(state, ticket)
    roles = {
        **{ref: "implementation_input" for ref in effective["implementation_input_refs"]},
        **{ref: "specification" for ref in effective["specification_refs"]},
    }
    contracts = {item.get("id"): item for item in state.get("contracts", [])}
    contract_bindings = []
    for ref in sorted(contract_refs):
        contract = contracts.get(ref)
        if contract is None:
            fail(f"execution binding references an unknown contract: {ref}")
        contract_bindings.append({
            "ref": ref,
            "version": contract.get("version"),
            "role": roles.get(ref),
            "implementation_availability": contract.get("implementation_availability", "unknown"),
            "evidence_refs": sorted(contract.get("implementation_availability_evidence_refs", [])),
        })

    candidate = current_candidate_record(state, ticket)
    expected_base = candidate.get("sha") if candidate is not None else state.get("repository", {}).get("initial_head")
    packet_base = packet.get("workspace", {}).get("expected_base")
    if not expected_base or packet_base != expected_base:
        fail("worker packet base SHA does not match the exact current ticket candidate/base")
    execution_root = state.get("repository", {}).get("execution_root")
    packet_root = packet.get("workspace", {}).get("root")
    try:
        if not execution_root or Path(packet_root).expanduser().resolve() != Path(execution_root).expanduser().resolve():
            fail("worker packet workspace root does not match the registered execution root")
    except (OSError, TypeError, ValueError):
        fail("worker packet workspace root is invalid")

    if packet.get("risk", {}).get("level") != ticket.get("risk"):
        fail("worker packet risk does not match the authoritative ticket risk")
    allow = packet_write_zone(packet)
    deny = sorted({relative_path(item, "packet write deny path").rstrip("/") for item in packet.get("write", {}).get("deny", [])})
    for entry in allow:
        for denied_path in deny:
            if entry["path"] == denied_path or entry["path"].startswith(denied_path + "/") or denied_path.startswith(entry["path"] + "/"):
                fail(f"packet write allow/deny overlap: {entry['path']} conflicts with {denied_path}")

    published_routes = [item for item in state.get("routes", []) if item.get("id") == route_id]
    if route is not None:
        supplied_route = copy.deepcopy(route)
        supplied_route.setdefault("id", route_id)
        if len(published_routes) > 1 or (published_routes and supplied_route != published_routes[0]):
            fail("supplied route differs from the exact route in the current design publication")
        route = supplied_route
    elif len(published_routes) == 1:
        route = published_routes[0]
    elif len(published_routes) > 1:
        fail("execution binding route is ambiguous in the current ledger")
    else:
        route = None
    if route is not None:
        validate_route_eligibility(route)
        route_hash = sha256_bytes(canonical_bytes(route))
    else:
        route_hash = None

    binding = {
        "version": 1,
        "run_id": state["run_id"],
        "ticket_id": ticket["id"],
        "attempt_id": attempt_id,
        "kind": kind,
        "mode": packet["mode"],
        "epoch": epoch,
        "packet_hash": packet_hash,
        "design_publication_ref": publication["id"],
        "design_publication_hash": publication["publication_hash"],
        "design_publication_revision": publication["published_revision"],
        "intent_revision": intent["revision"],
        "intent_document_ref": intent["document_ref"],
        "intent_document_hash": intent["document_hash"],
        "base_sha": expected_base,
        "criterion_refs": sorted(ticket_criteria),
        "contract_bindings": contract_bindings,
        "allow": allow,
        "deny": deny,
        "risk": copy.deepcopy(packet.get("risk")),
        "route_id": route_id,
        "route_hash": route_hash,
    }
    root_schema = schema()
    validate(binding, root_schema["$defs"]["execution_binding"], root_schema, "$.execution_binding")
    binding_hash = sha256_bytes(canonical_bytes(binding))

    if return_identity is not None:
        expected_return_identity = {
            "run_id": binding["run_id"], "ticket_id": binding["ticket_id"],
            "attempt_id": binding["attempt_id"], "epoch": binding["epoch"],
            "packet_hash": binding["packet_hash"],
            "intent_revision": binding["intent_revision"],
            "intent_document_ref": binding["intent_document_ref"],
            "intent_document_hash": binding["intent_document_hash"],
            "design_publication_ref": binding["design_publication_ref"],
            "design_publication_hash": binding["design_publication_hash"],
            "design_publication_revision": binding["design_publication_revision"],
            "contract_refs": sorted(contract_refs),
        }
        if any(return_identity.get(field) != expected for field, expected in expected_return_identity.items()):
            fail("worker return identity does not exactly match its execution binding")

    if attempt is not None:
        if (
            attempt.get("kind") != kind or attempt.get("mode") != packet.get("mode")
            or attempt.get("subject_ref") != ticket.get("id")
            or attempt.get("epoch") != epoch or attempt.get("packet_hash") != packet_hash
            or attempt.get("base_sha") != expected_base or attempt.get("route_ref") != route_id
        ):
            fail("registered attempt identity or scope differs from its execution binding")
        if attempt.get("execution_binding") != binding or attempt.get("execution_binding_hash") != binding_hash:
            fail("registered execution binding is missing, stale, or altered")
    return binding


def active_repair_authorization(state: dict[str, Any], ticket_id: str, finding_ref: str) -> dict[str, Any] | None:
    matches = [
        item for item in state.get("decisions", [])
        if item.get("type") == "repair_authorization"
        and item.get("status") == "authorized"
        and item.get("decision") == "REPAIR"
        and ticket_id in item.get("affected_refs", [])
        and finding_ref in item.get("affected_refs", [])
        and not item.get("invalidated_by")
    ]
    return matches[-1] if matches else None


def repair_finding_refs(repair: dict[str, Any]) -> list[str]:
    """Read both the v1.0 scalar contract and the canonical grouped contract."""
    refs = repair.get("finding_refs")
    if isinstance(refs, list):
        return list(refs)
    finding_ref = repair.get("finding_ref")
    return [finding_ref] if isinstance(finding_ref, str) else []


def effective_finding_ticket_refs(state: dict[str, Any], finding_ref: str) -> list[str]:
    """Return raw ticket refs plus exact active append-only finding reconciliations."""
    ticket_ids = {item.get("id") for item in state.get("tickets", [])}
    finding = next((item for item in state.get("findings", []) if item.get("id") == finding_ref), None)
    issue = next((item for item in state.get("issues", []) if item.get("id") == finding_ref), None)
    if issue and issue.get("finding_ref"):
        finding = next((item for item in state.get("findings", []) if item.get("id") == issue.get("finding_ref")), finding)
    refs = {ref for ref in (finding or issue or {}).get("affected_refs", []) if ref in ticket_ids}
    if finding is None:
        return sorted(refs)
    for event in state.get("finding_binding_reconciliations", []):
        ticket = next((item for item in state.get("tickets", []) if item.get("id") == event.get("ticket_ref")), None)
        candidate = next((item for item in state.get("candidates", []) if item.get("id") == event.get("candidate_ref")), None)
        attempt = next((item for item in state.get("attempts", []) if item.get("id") == event.get("review_attempt_ref")), None)
        if (
            ticket is None or candidate is None or attempt is None
            or ticket.get("current_candidate") != candidate.get("id")
            or candidate.get("sha") != event.get("candidate_sha")
            or candidate.get("tree_sha") != event.get("candidate_tree_sha")
            or attempt.get("subject_ref") != ticket.get("id")
            or attempt.get("candidate_sha") != event.get("candidate_sha")
            or attempt.get("packet_ref") != event.get("packet_ref")
            or attempt.get("packet_hash") != event.get("packet_hash")
            or attempt.get("return_ref") != event.get("return_ref")
        ):
            continue
        for binding in event.get("finding_bindings", []):
            if binding.get("finding_ref") != finding.get("id"):
                continue
            mirror = next((item for item in state.get("issues", []) if item.get("id") == binding.get("issue_ref")), None)
            if mirror and mirror.get("finding_ref") == finding.get("id") and mirror.get("source_ref") == attempt.get("id") and finding.get("source_ref") == attempt.get("id"):
                refs.add(ticket["id"])
    return sorted(refs)


def repair_proofs(repair: dict[str, Any]) -> list[dict[str, str]]:
    """Return one normalized hypothesis/proof pair for each selected finding."""
    proofs = repair.get("finding_proofs")
    if isinstance(proofs, list):
        return [
            {"finding_ref": item["finding_ref"], "hypothesis": item["hypothesis"], "expected_proof": item["expected_proof"]}
            for item in proofs
        ]
    finding_ref = repair.get("finding_ref")
    if not isinstance(finding_ref, str):
        return []
    return [{
        "finding_ref": finding_ref,
        "hypothesis": repair.get("hypothesis", ""),
        "expected_proof": repair.get("expected_proof", ""),
    }]


def repair_signature(contract: dict[str, Any]) -> str:
    """Hash the causal repair intent, treating a legacy singleton as a group."""
    refs = repair_finding_refs(contract)
    proofs = sorted(repair_proofs(contract), key=lambda item: item["finding_ref"])
    payload = {
        "cause": contract.get("cause"),
        "finding_refs": sorted(refs),
        "finding_proofs": proofs,
        "stopping_condition": contract.get("stopping_condition"),
        "causal_change": contract.get("causal_change"),
    }
    return sha256_bytes(canonical_bytes(payload))


def normalize_repair_contract(
    state: dict[str, Any], ticket: dict[str, Any], contract: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the bounded candidate-bound RepairPlan shared by authorization and dispatch."""
    refs = repair_finding_refs(contract)
    proofs = repair_proofs(contract)
    if not refs or len(refs) > 16 or len(refs) != len(set(refs)):
        fail("repair plan finding_refs must be bounded, non-empty, and unique")
    proof_by_ref = {item.get("finding_ref"): item for item in proofs}
    if len(proof_by_ref) != len(proofs) or set(proof_by_ref) != set(refs):
        fail("repair plan requires exactly one hypothesis and expected_proof per selected finding")
    proofs = [proof_by_ref[ref] for ref in sorted(refs)]
    for item in proofs:
        nonempty_string(item.get("hypothesis"), f"repair hypothesis for {item['finding_ref']}")
        nonempty_string(item.get("expected_proof"), f"repair expected_proof for {item['finding_ref']}")
    source_attempt = current_candidate_producer(state, ticket)
    candidate = current_candidate_record(state, ticket)
    if source_attempt is None or candidate is None or not source_attempt.get("candidate_sha"):
        fail("repair plan requires an explicit current candidate binding and its producing worker")
    source_ref = contract.get("source_attempt_ref")
    if source_ref:
        supplied = next((item for item in state.get("attempts", []) if item.get("id") == source_ref), None)
        if supplied is None or supplied.get("subject_ref") != ticket.get("id"):
            fail("repair requires same-ticket source_attempt_ref provenance for the current candidate worker or exact review")
        if supplied.get("kind") == "review":
            if (
                supplied.get("candidate_sha") != candidate.get("sha")
                or supplied.get("subject_fingerprint") not in (None, candidate.get("sha"))
                or any(ref not in supplied.get("finding_refs", []) for ref in refs)
            ):
                fail("repair source review is not the exact same-ticket review for every selected current finding")
        elif supplied.get("kind") != "worker" or supplied.get("id") != source_attempt.get("id"):
            fail("repair source_attempt_ref provenance is stale or is not the current candidate producer")
    proof_records: list[dict[str, Any]] = []
    for finding_ref in sorted(refs):
        finding = next((item for item in state.get("findings", []) if item.get("id") == finding_ref), None)
        issue = next((item for item in state.get("issues", []) if item.get("id") == finding_ref), None)
        record = finding or issue
        if record is None or record.get("impact") != "blocking" or record.get("invalidated_by"):
            fail(f"repair finding is not a current blocking finding/issue: {finding_ref}")
        if ticket.get("id") not in effective_finding_ticket_refs(state, finding_ref):
            fail(f"repair finding is not bound to this ticket: {finding_ref}")
        if not finding_matches_candidate(state, finding_ref, ticket["id"], candidate["sha"]):
            fail(f"repair finding is not bound to the current candidate: {finding_ref}")
        proof_records.append(proof_by_ref[finding_ref])
    canonical = {
        "cause": contract.get("cause"),
        "finding_refs": sorted(refs),
        "finding_proofs": proof_records,
        "stopping_condition": contract.get("stopping_condition"),
        "causal_change": contract.get("causal_change"),
        "source_attempt_ref": source_attempt["id"],
    }
    repair_plan = {
        "version": 1,
        **canonical,
        "source_candidate_ref": candidate["id"],
        "source_candidate_sha": candidate["sha"],
    }
    root = schema()
    validate(repair_plan, root["$defs"]["repair_plan"], root, "$.repair_plan")
    return canonical, repair_plan


def build_attempt_plan(
    state: dict[str, Any], ticket: dict[str, Any], packet: dict[str, Any], route_id: str,
    route: dict[str, Any] | None, packet_hash: str, p: dict[str, Path] | None = None,
) -> dict[str, Any]:
    """Freeze the packet fields which define dispatch feasibility and identity."""
    if p is None:
        control_root = state.get("repository", {}).get("control_root")
        if not control_root:
            fail("attempt plan requires the registered control root for execution binding")
        p = paths(control_root, state["run_id"])
    execution_binding = validate_execution_binding(
        p, state, ticket, packet, kind="worker",
        attempt_id=packet_identity(packet).get("attempt_id"), packet_hash=packet_hash,
        route_id=route_id, route=route,
    )
    identity = packet_identity(packet)
    if identity.get("run_id") != state.get("run_id") or identity.get("ticket_id") != ticket.get("id"):
        fail("attempt plan packet must bind the current run and exact ticket")
    if identity.get("epoch") != state.get("owner", {}).get("epoch"):
        fail("attempt plan packet epoch does not match current owner")
    base_sha = packet.get("workspace", {}).get("expected_base")
    candidate = current_candidate_record(state, ticket)
    if candidate is None or base_sha != candidate.get("sha"):
        fail("attempt plan base SHA is stale or forked from the exact current candidate")
    binding = current_intent_binding(state) if state.get("intent") else None
    packet_intent = packet.get("intent_revision") or identity.get("intent_revision")
    packet_hash_value = packet.get("intent_document_hash") or identity.get("intent_document_hash")
    if binding and (packet_intent != binding["revision"] or packet_hash_value != binding["document_hash"]):
        fail("attempt plan intent revision/hash must exactly match current intent")
    if binding is None and (packet_intent or packet_hash_value):
        fail("attempt plan carries an intent binding when the run has no current intent")
    allow = packet_write_zone(packet)
    deny = sorted({relative_path(item, "packet write deny path").rstrip("/") for item in packet.get("write", {}).get("deny", [])})
    for entry in allow:
        for denied_path in deny:
            if entry["path"] == denied_path or entry["path"].startswith(denied_path + "/") or denied_path.startswith(entry["path"] + "/"):
                fail(f"packet write allow/deny overlap: {entry['path']} conflicts with {denied_path}")
    criteria = [item.get("criterion_id") for item in packet.get("acceptance", [])]
    if not criteria or len(criteria) != len(set(criteria)):
        fail("attempt plan acceptance criteria must be non-empty and unique")
    checks = packet.get("verification", [])
    check_ids = [item.get("check_id") for item in checks]
    if not check_ids or len(check_ids) != len(set(check_ids)):
        fail("attempt plan verification checks must be non-empty and unique")
    if route is not None:
        validate_route_eligibility(route)
    route_hash = sha256_bytes(canonical_bytes(route)) if route is not None else None
    plan = {
        "version": 1,
        "run_id": state["run_id"],
        "ticket_id": ticket["id"],
        "attempt_id": identity.get("attempt_id"),
        "route_id": route_id,
        "route_hash": route_hash,
        "packet_hash": packet_hash,
        "base_sha": base_sha,
        "epoch": identity.get("epoch"),
        "intent_revision": binding["revision"] if binding else None,
        "intent_document_hash": binding["document_hash"] if binding else None,
        "execution_binding_hash": sha256_bytes(canonical_bytes(execution_binding)),
        "allow": allow,
        "deny": deny,
        "risk": copy.deepcopy(packet.get("risk")),
        "criterion_refs": sorted(criteria),
        "checks": sorted((copy.deepcopy(item) for item in checks), key=lambda item: item.get("check_id", "")),
    }
    root = schema()
    validate(plan, root["$defs"]["attempt_plan"], root, "$.attempt_plan")
    return plan


def repair_authorization_for_attempt(state: dict[str, Any], ticket_id: str, repair: dict[str, Any], attempt_id: str) -> dict[str, Any] | None:
    refs = set(repair_finding_refs(repair))
    matches = [
        item for item in state.get("decisions", [])
        if item.get("type") == "repair_authorization"
        and item.get("decision") == "REPAIR"
        and item.get("status") in ("authorized", "consumed")
        and ticket_id in item.get("affected_refs", [])
        and refs.issubset(set(item.get("affected_refs", [])))
        and (item.get("status") == "authorized" or item.get("consumed_by") == attempt_id)
        and not item.get("invalidated_by")
    ]
    return matches[-1] if matches else None


def validate_repair_authorization(
    p: dict[str, Path], state: dict[str, Any], ticket_id: str, repair: dict[str, Any],
    *, attempt_id: str | None = None, authorization_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    refs = repair_finding_refs(repair)
    authorizations = [active_repair_authorization(state, ticket_id, ref) for ref in refs]
    if authorization_override is not None:
        authorization = authorization_override
    elif refs and all(authorizations) and len({item.get("id") for item in authorizations if item}) == 1:
        authorization = authorizations[0]
    else:
        fail("repair dispatch requires one active authorization for the exact ticket and finding set")
    if authorization.get("status") != "authorized":
        fail("repair authorization is not unused and authorized")
    if not set(refs).issubset(set(authorization.get("affected_refs", []))):
        fail("repair authorization does not cover the exact selected finding set")
    prior_uses = [item for item in state.get("attempts", []) if item.get("repair_authorization_ref") == authorization.get("id")]
    if prior_uses:
        fail("repair authorization was already consumed; authorize a changed repair before another dispatch")
    if authorization_override is not None and authorization_override.get("id") == "preflight":
        return authorization
    repair_ref = authorization.get("repair_plan_ref")
    if repair_ref:
        authorized_plan = stored_payload(p, repair_ref, "authorized RepairPlan")
        expected_contract, expected_plan = normalize_repair_contract(
            state, next(item for item in state.get("tickets", []) if item.get("id") == ticket_id), repair
        )
        authorized_contract = {key: authorized_plan.get(key) for key in expected_plan if key != "version"}
        if authorized_contract != {key: expected_plan.get(key) for key in expected_plan if key != "version"}:
            fail("repair packet contract does not match the authorized canonical RepairPlan")
    else:
        contract_refs = [ref for ref in authorization.get("evidence_refs", []) if isinstance(ref, str) and ref.startswith("objects/")]
        if len(contract_refs) != 1:
            fail("legacy repair authorization lacks one exact repair contract object binding")
        authorized_contract = stored_payload(p, contract_refs[0], "authorized repair contract")
        ticket = next((item for item in state.get("tickets", []) if item.get("id") == ticket_id), None)
        if ticket is None:
            fail("repair authorization references an unknown ticket")
        authorized_contract, _ = normalize_repair_contract(state, ticket, authorized_contract)
        packet_contract, _ = normalize_repair_contract(state, ticket, repair)
        if authorized_contract != packet_contract:
            fail("repair packet contract does not match the authorized repair contract")
    return authorization


def repair_preflight(
    p: dict[str, Path], state: dict[str, Any], ticket: dict[str, Any], repair: dict[str, Any],
    *, packet: dict[str, Any] | None = None, route_id: str | None = None,
    route: dict[str, Any] | None = None, packet_hash: str | None = None,
    authorization: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None, tuple[list[dict[str, Any]], dict[str, Any] | None] | None]:
    """Shared authorize/dispatch admission for repair and its exact AttemptPlan."""
    canonical, repair_plan = normalize_repair_contract(state, ticket, repair)
    for dependency in ticket.get("dependency_refs", []):
        dependency_ticket = next((item for item in state.get("tickets", []) if item.get("id") == dependency), None)
        if dependency_ticket is None or dependency_ticket.get("state") != "INTEGRATED":
            fail(f"repair AttemptPlan dependency is not current INTEGRATED: {dependency}")
    if any(
        item.get("id") != ticket.get("id") and item.get("state") in ("RUNNING", "CANDIDATE", "REVIEW")
        for item in state.get("tickets", [])
    ):
        fail("serial V1 product writer already active")
    projection = finding_obligation_projection(state)
    for finding_ref in repair_plan["finding_refs"]:
        finding = next((item for item in state.get("findings", []) if item.get("id") == finding_ref), None)
        if finding is not None:
            projected = next((item for item in projection["items"] if item.get("finding_ref") == finding_ref), None)
            unresolved = projected.get("unresolved_ticket_refs", projected.get("affected_ticket_refs", [])) if projected else []
            if projected is None or not projected.get("repairable") or ticket["id"] not in unresolved:
                fail(f"repair authorization requires a current repairable finding obligation: {finding_ref}")
        else:
            projected = next((item for item in projection["mirrored_issues"] if item.get("issue_ref") == finding_ref), None)
            if projected is None or not projected.get("repairable"):
                fail(f"repair authorization requires a current repairable issue obligation: {finding_ref}")
    if (
        not repair.get("source_attempt_ref")
        and repair_requires_transitive_create_modify_provenance(p, state, ticket)
    ):
        fail("repair lease expansion requires explicit source_attempt_ref provenance")
    if packet is None:
        if len(repair_plan["finding_refs"]) != 1:
            fail("grouped RepairPlan authorization requires --packet for dispatch preflight")
        return canonical, repair_plan, None, None
    if packet.get("kind") != "worker" or packet.get("mode") != "repair" or packet.get("repair") != repair:
        fail("repair AttemptPlan requires a repair worker packet with the exact supplied repair contract")
    if route_id is None:
        fail("repair AttemptPlan authorization requires --route-id")
    if packet_hash is None:
        packet_hash = sha256_bytes(canonical_bytes(packet))
    if authorization is not None and authorization.get("legacy_unbound_attempt_plan"):
        lease_result = effective_worker_lease(
            p, state, ticket, {**packet, "repair": canonical},
            authorization_override=authorization,
        )
        return canonical, repair_plan, None, lease_result
    attempt_plan = build_attempt_plan(state, ticket, packet, route_id, route, packet_hash, p)
    normalized_packet = copy.deepcopy(packet)
    normalized_packet["repair"] = canonical
    lease_result = effective_worker_lease(
        p, state, ticket, normalized_packet,
        authorization_override=authorization or {
            "id": "preflight", "status": "authorized",
            "affected_refs": [ticket["id"], *repair_plan["finding_refs"]],
        },
    )
    signature = repair_signature(canonical)
    for previous in state.get("attempts", []):
        if previous.get("subject_ref") != ticket.get("id") or not previous.get("repair_contract"):
            continue
        previous_signature = previous.get("failure_signature") or repair_signature(previous.get("repair_contract", {}))
        if previous_signature == signature:
            fail("unchanged repair retry rejected before READY: no causally meaningful change")
    return canonical, repair_plan, attempt_plan, lease_result


def finding_matches_candidate(state: dict[str, Any], finding_ref: str, ticket_id: str, candidate_sha: str) -> bool:
    """Prove that the authorized finding was raised against this candidate."""
    finding = next((item for item in state.get("findings", []) if item.get("id") == finding_ref), None)
    issue = next((item for item in state.get("issues", []) if item.get("id") == finding_ref), None)
    if issue and issue.get("finding_ref"):
        finding = next((item for item in state.get("findings", []) if item.get("id") == issue.get("finding_ref")), finding)
    record = finding or issue
    if record is None or record.get("impact") != "blocking" or record.get("invalidated_by"):
        return False
    if ticket_id not in effective_finding_ticket_refs(state, finding_ref):
        return False
    source_ref = record.get("source_ref")
    source_attempt = next((item for item in state.get("attempts", []) if item.get("id") == source_ref), None)
    if source_attempt is not None:
        if source_attempt.get("kind") == "review":
            return (
                source_attempt.get("subject_ref") == ticket_id
                and source_attempt.get("candidate_sha") == candidate_sha
                and source_attempt.get("subject_fingerprint") in (None, candidate_sha)
            )
        if source_attempt.get("kind") == "worker":
            return (
                source_attempt.get("subject_ref") == ticket_id
                and (
                    source_attempt.get("candidate_sha") == candidate_sha
                    or record is issue
                    and source_attempt.get("candidate_sha") is None
                    and source_attempt.get("base_sha") == candidate_sha
                )
            )
        return False
    source_review = next((item for item in state.get("reviews", []) if item.get("id") == source_ref), None)
    return bool(source_review and source_review.get("subject_fingerprint") == candidate_sha and ticket_id in effective_finding_ticket_refs(state, finding_ref))


def continuation_candidate_receipt(
    p: dict[str, Path], state: dict[str, Any], ticket: dict[str, Any], attempt: dict[str, Any]
) -> dict[str, Any] | None:
    """Return an integrity-checked BLOCKED/HANDOFF candidate continuation record."""
    receipt_ref = attempt.get("continuation_ref")
    authorization_ref = attempt.get("continuation_authorization_ref")
    if not receipt_ref or not authorization_ref:
        return None
    receipt = stored_payload(p, receipt_ref, "continuation candidate receipt")
    authorization = next(
        (
            item for item in state.get("decisions", [])
            if item.get("id") == authorization_ref
            and item.get("type") == "continuation_candidate_authorization"
            and item.get("status") == "applied"
            and item.get("decision") == "PRESERVE_CONTINUATION"
            and ticket.get("id") in item.get("affected_refs", [])
            and attempt.get("id") in item.get("affected_refs", [])
            and not item.get("invalidated_by")
        ),
        None,
    )
    if authorization is None:
        fail("continuation candidate lacks its current owner authorization")
    returned = stored_payload(p, attempt.get("return_ref"), "continuation candidate worker return")
    expected = {
        "run_id": state.get("run_id"),
        "ticket_id": ticket.get("id"),
        "attempt_id": attempt.get("id"),
        "return_ref": attempt.get("return_ref"),
        "authorization_ref": authorization_ref,
        "blocker_ref": authorization.get("blocker_ref"),
        "blocker_scope": authorization.get("blocker_scope"),
        "base_sha": attempt.get("base_sha"),
        "candidate_sha": attempt.get("candidate_sha"),
        "candidate_tree_sha": attempt.get("candidate_tree_sha"),
        "return_status": returned.get("status"),
        "files": returned.get("files"),
        "lease_zone": attempt.get("lease", {}).get("zone"),
        "external_check_ids": sorted(authorization.get("external_check_ids", [])),
        "external_criterion_ids": sorted(authorization.get("external_criterion_ids", [])),
    }
    if any(receipt.get(key) != value for key, value in expected.items()):
        fail("continuation candidate receipt does not match the attempt, return, authorization, or lease")
    if returned.get("status") not in ("BLOCKED", "HANDOFF"):
        fail("continuation candidate source is not a BLOCKED/HANDOFF worker return")
    audit = receipt.get("write_set_audit")
    if not isinstance(audit, dict) or audit.get("pass") is not True or not audit.get("changed_paths"):
        fail("continuation candidate source has no passing non-empty write-set audit")
    if receipt.get("audit_hash") != sha256_bytes(canonical_bytes(audit)):
        fail("continuation candidate write-set audit hash does not match")
    if receipt.get("blocker_ref") != authorization.get("blocker_ref"):
        fail("continuation candidate blocker binding is discontinuous")
    commit_ref = receipt.get("commit_receipt_ref")
    commit_receipt = stored_payload(p, commit_ref, "continuation candidate commit receipt")
    if (
        commit_receipt.get("status") != "PASS"
        or commit_receipt.get("authority_ref") != authorization_ref
        or commit_receipt.get("base_sha") != attempt.get("base_sha")
        or commit_receipt.get("commit_sha") != attempt.get("candidate_sha")
        or commit_receipt.get("tree_sha") != attempt.get("candidate_tree_sha")
    ):
        fail("continuation candidate commit receipt no longer matches its authorization and Git object")
    checkout = Path(attempt.get("checkout") or "").expanduser().resolve()
    regular_directory(checkout, "continuation candidate checkout")
    try:
        tree_sha = git_output(checkout, "rev-parse", f"{attempt['candidate_sha']}^{{tree}}").decode().strip()
        parents = git_output(checkout, "rev-list", "--parents", "-n", "1", attempt["candidate_sha"]).decode().split()
    except (OSError, UnicodeError) as exc:
        fail(f"cannot revalidate continuation candidate Git object: {exc}")
    if tree_sha != attempt.get("candidate_tree_sha") or len(parents) != 2 or parents[1] != attempt.get("base_sha"):
        fail("continuation candidate Git object has a missing or discontinuous base/tree edge")
    return receipt


def validated_candidate_worker_return(
    p: dict[str, Path], state: dict[str, Any], ticket: dict[str, Any], attempt: dict[str, Any]
) -> dict[str, Any]:
    """Validate a current candidate return, including an authorized continuation."""
    returned = stored_payload(p, attempt.get("return_ref"), "candidate worker return")
    root = schema()
    validate(returned, root["$defs"]["worker_return"], root, "$.candidate_worker_return")
    identity = packet_identity(returned)
    if (
        identity.get("run_id") != state.get("run_id")
        or identity.get("ticket_id") != ticket.get("id")
        or identity.get("attempt_id") != attempt.get("id")
        or identity.get("packet_hash") != attempt.get("packet_hash")
        or identity.get("epoch") != attempt.get("epoch")
    ):
        fail("candidate worker return identity is not bound to its current attempt")
    if returned.get("status") == "DONE":
        return returned
    if returned.get("status") in ("BLOCKED", "HANDOFF"):
        if continuation_candidate_receipt(p, state, ticket, attempt) is not None:
            return returned
    fail("candidate worker return is neither DONE nor an authorized continuation")


def current_candidate_record(state: dict[str, Any], ticket: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve only an explicit current-candidate pointer; legacy attempt pointers are not promoted."""
    candidate_id = ticket.get("current_candidate")
    if candidate_id is None:
        return None
    matches = [item for item in state.get("candidates", []) if item.get("id") == candidate_id]
    if len(matches) != 1 or matches[0].get("ticket_ref") != ticket.get("id"):
        fail(f"ticket current_candidate pointer is missing, ambiguous, or cross-ticket: {ticket.get('id')}")
    return matches[0]


def current_candidate_producer(state: dict[str, Any], ticket: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve the producer for the explicit candidate, with a conservative legacy fallback."""
    candidate = current_candidate_record(state, ticket)
    if candidate is not None:
        producer = next((item for item in state.get("attempts", []) if item.get("id") == candidate.get("producer_attempt_ref")), None)
        if producer is None or producer.get("kind") != "worker" or producer.get("subject_ref") != ticket.get("id"):
            fail(f"current candidate producer is not a same-ticket worker: {candidate.get('id')}")
        return producer
    if "current_candidate" in ticket and state.get("candidate_model_version") == "1.1":
        return None
    legacy = next((item for item in state.get("attempts", []) if item.get("id") == ticket.get("current_attempt")), None)
    if (
        legacy and legacy.get("kind") == "worker" and legacy.get("subject_ref") == ticket.get("id")
        and legacy.get("state") == "RETURNED" and legacy.get("candidate_sha")
    ):
        return legacy
    return None


def _ticket_blocking_refs(state: dict[str, Any], ticket_id: str) -> list[str]:
    refs = {
        item.get("id") for item in state.get("issues", [])
        if item.get("id") and item.get("impact") == "blocking"
        and not item.get("invalidated_by") and ticket_id in effective_finding_ticket_refs(state, item["id"])
    }
    refs.update(
        item.get("id") for item in state.get("findings", [])
        if item.get("id") and item.get("impact") == "blocking"
        and not item.get("invalidated_by") and ticket_id in effective_finding_ticket_refs(state, item["id"])
    )
    return sorted(refs)


def publish_candidate_projection(
    state: dict[str, Any], ticket: dict[str, Any], attempt: dict[str, Any], *,
    quality: str, blocker_refs: list[str] | tuple[str, ...] = (), proof_ref: str | None = None,
) -> dict[str, Any]:
    """Publish the explicit candidate identity and advance its independent ticket pointer."""
    if quality not in ("DONE", "CONTINUATION"):
        fail(f"invalid candidate quality: {quality}")
    if attempt.get("kind") != "worker" or attempt.get("subject_ref") != ticket.get("id"):
        fail("candidate producer must be a worker attempt for the same ticket")
    if not attempt.get("candidate_sha") or not attempt.get("candidate_tree_sha"):
        fail("candidate projection requires exact commit and tree SHAs")
    candidate_id = f"candidate-{attempt['id']}"
    candidates = state.setdefault("candidates", [])
    existing = next((item for item in candidates if item.get("id") == candidate_id), None)
    parent_ref = ticket.get("current_candidate")
    blockers = sorted(set(blocker_refs or _ticket_blocking_refs(state, ticket["id"])))
    record = {
        "id": candidate_id,
        "ticket_ref": ticket["id"],
        "sha": attempt["candidate_sha"],
        "tree_sha": attempt["candidate_tree_sha"],
        "base_sha": attempt.get("base_sha"),
        "producer_attempt_ref": attempt["id"],
        "parent_candidate_ref": parent_ref,
        "quality": quality,
        "blocker_refs": blockers,
        "review_status": "PENDING",
        "integration_status": "PENDING",
        "superseded_by": None,
        "invalidated_by": [],
    }
    if proof_ref is not None:
        record["proof_ref"] = proof_ref
    if existing is not None:
        comparable = {key: existing.get(key) for key in record}
        if comparable != record:
            fail(f"candidate ID already has conflicting projection: {candidate_id}")
        record = existing
    else:
        if parent_ref:
            parent = next((item for item in candidates if item.get("id") == parent_ref), None)
            if parent is None or parent.get("ticket_ref") != ticket["id"]:
                fail("candidate parent pointer does not resolve to a same-ticket candidate")
            if parent.get("superseded_by") not in (None, candidate_id):
                fail("candidate parent was already superseded by another candidate")
            parent["superseded_by"] = candidate_id
        candidates.append(record)
    ticket["current_candidate"] = candidate_id
    ticket["last_worker_attempt"] = attempt["id"]
    ticket["current_attempt"] = attempt["id"]
    return record


def build_verified_candidate_proof(
    p: dict[str, Path], state: dict[str, Any], ticket: dict[str, Any], attempt: dict[str, Any],
    operation: dict[str, Any], operation_id: str, commit_receipt: dict[str, Any], commit_receipt_raw: bytes,
    *, quality: str, parent_candidate_ref: str | None,
) -> tuple[dict[str, Any], str]:
    """Build one identity-, Git-, and write-set-bound proof for every candidate quality."""
    if quality not in ("DONE", "CONTINUATION"):
        fail(f"invalid verified candidate quality: {quality}")
    if (
        operation.get("id") != operation_id or operation.get("kind") != "candidate_commit"
        or operation.get("state") not in ("prepared", "applied")
        or operation.get("authority_ref") is None
    ):
        fail("verified candidate requires the exact prepared/applied candidate_commit operation")
    if attempt.get("kind") != "worker" or attempt.get("subject_ref") != ticket.get("id"):
        fail("verified candidate producer must be a same-ticket worker attempt")
    if attempt.get("state") != "RETURNED" or attempt.get("lease", {}).get("state") != "active":
        fail("verified candidate requires a returned attempt with an active, non-quarantined lease")
    if attempt.get("epoch") != state.get("owner", {}).get("epoch"):
        fail("verified candidate producer belongs to a stale owner epoch")
    packet_ref = attempt.get("packet_ref")
    returned_ref = attempt.get("return_ref")
    if not packet_ref or not returned_ref or not attempt.get("packet_hash"):
        fail("verified candidate requires immutable packet and return references")
    packet = stored_payload(p, packet_ref, "candidate worker packet")
    worker_return = stored_payload(p, returned_ref, "candidate worker return")
    root = schema()
    validate(worker_return, root["$defs"]["worker_return"], root, "$.candidate_worker_return")
    validate_worker_return_semantics(worker_return, packet)
    identity = packet_identity(worker_return)
    packet_identity_value = packet_identity(packet)
    if (
        identity.get("run_id") != state.get("run_id")
        or identity.get("ticket_id") != ticket.get("id")
        or identity.get("attempt_id") != attempt.get("id")
        or identity.get("packet_hash") != attempt.get("packet_hash")
        or identity.get("epoch") != attempt.get("epoch")
        or packet_identity_value.get("attempt_id") != attempt.get("id")
        or packet_identity_value.get("ticket_id") not in (None, ticket.get("id"))
    ):
        fail("verified candidate packet/return identity is not bound to the current attempt")
    expected_status = "DONE" if quality == "DONE" else worker_return.get("status")
    if worker_return.get("status") != expected_status or (
        quality == "CONTINUATION" and worker_return.get("status") not in ("BLOCKED", "HANDOFF")
    ):
        fail("candidate quality does not match the exact worker return status")

    base_sha = attempt.get("base_sha")
    if not GIT_SHA_RE.fullmatch(base_sha or ""):
        fail("verified candidate requires an exact committed Git base SHA")
    checkout_value = attempt.get("checkout")
    if not isinstance(checkout_value, str) or not checkout_value:
        fail("verified candidate attempt has no exact Git checkout")
    checkout = Path(checkout_value).expanduser().resolve()
    regular_directory(checkout, "verified candidate checkout")
    target_value = operation.get("target")
    if not isinstance(target_value, str) or not target_value:
        fail("candidate effect operation has no exact target")
    target = Path(target_value).expanduser().resolve()
    if target != checkout:
        fail("candidate effect target does not match the worker's exact checkout")
    if operation.get("expected_before") != base_sha:
        fail("candidate effect expected-before does not match the worker's exact base")
    if operation.get("intended_after") not in (None, commit_receipt.get("commit_sha")):
        fail("candidate receipt does not match the operation's intended-after SHA")
    if commit_receipt.get("status") != "PASS":
        fail("candidate commit receipt must have status PASS")
    candidate_sha = commit_receipt.get("commit_sha")
    tree_sha = commit_receipt.get("tree_sha")
    if not GIT_SHA_RE.fullmatch(candidate_sha or "") or not GIT_SHA_RE.fullmatch(tree_sha or ""):
        fail("candidate receipt must bind valid commit and tree SHAs")
    if not commit_receipt.get("checkout"):
        fail("candidate commit receipt must bind the exact checkout")
    if Path(commit_receipt["checkout"]).expanduser().resolve() != checkout:
        fail("candidate commit receipt checkout does not match the exact worker checkout")
    if commit_receipt.get("base_sha") != base_sha:
        fail("candidate commit receipt does not bind the exact worker base")
    if commit_receipt.get("authority_ref") != operation.get("authority_ref"):
        fail("candidate commit receipt does not bind the operation authority")
    receipt_identity = {
        "run_id": state.get("run_id"),
        "ticket_id": ticket.get("id"),
        "attempt_id": attempt.get("id"),
        "operation_id": operation_id,
        "kind": "candidate_commit",
        "expected_before": base_sha,
        "intended_after": candidate_sha,
    }
    if any(commit_receipt.get(key) != value for key, value in receipt_identity.items()):
        fail("candidate commit receipt does not bind the exact run, ticket, attempt, operation, target, base, and intended commit")
    if not commit_receipt.get("target") or Path(commit_receipt["target"]).expanduser().resolve() != target:
        fail("candidate commit receipt does not bind the exact operation target")
    if not worker_return.get("files"):
        fail("candidate proof requires a non-empty declared worker write set")

    try:
        actual_head = git_output(checkout, "rev-parse", "HEAD").decode().strip()
        actual_tree = git_output(checkout, "rev-parse", "HEAD^{tree}").decode().strip()
        parents = git_output(checkout, "rev-list", "--parents", "-n", "1", actual_head).decode().split()
    except (OSError, UnicodeError) as exc:
        fail(f"cannot inspect verified candidate Git object: {exc}")
    if actual_head != candidate_sha or actual_tree != tree_sha:
        fail("candidate receipt does not match the exact checkout HEAD and tree")
    if len(parents) != 2 or parents[1] != base_sha:
        fail("candidate commit must be one direct commit on the exact worker base")
    if git_output(checkout, "status", "--porcelain=v1", "-z", "--untracked-files=all"):
        fail("candidate checkout must be clean after its exact candidate commit")

    baseline = git_tree_baseline(checkout, base_sha)
    audit = audit_write_set(checkout, baseline, worker_return.get("files", []), attempt.get("lease", {}).get("zone", []))
    if not audit.get("pass") or not audit.get("changed_paths"):
        fail(f"candidate write-set audit must PASS with a non-empty exact delta: {json.dumps(audit, sort_keys=True)}")
    if set(audit.get("changed_paths", [])) != {item.get("path") for item in worker_return.get("files", [])}:
        fail("candidate write-set audit differs from the exact validated worker return")

    commit_ref = f"objects/{object_store(p, bytes(commit_receipt_raw))}"
    audit_raw = canonical_bytes(audit)
    audit_ref = f"objects/{object_store(p, audit_raw)}"
    proof = {
        "version": "1.1",
        "run_id": state["run_id"],
        "ticket_id": ticket["id"],
        "attempt_id": attempt["id"],
        "operation_id": operation_id,
        "quality": quality,
        "candidate_sha": candidate_sha,
        "candidate_tree_sha": tree_sha,
        "base_sha": base_sha,
        "parent_sha": parents[1],
        "checkout": str(checkout),
        "target": str(target),
        "authority_ref": operation["authority_ref"],
        "parent_candidate_ref": parent_candidate_ref,
        "packet_ref": packet_ref,
        "packet_hash": attempt["packet_hash"],
        "return_ref": returned_ref,
        "commit_receipt_ref": commit_ref,
        "write_set_audit_ref": audit_ref,
        "write_set_audit_hash": sha256_bytes(audit_raw),
        "introduced_revision": state["revision"] + 1,
    }
    validate(proof, root["$defs"]["verified_candidate_proof"], root, "$.verified_candidate_proof")
    proof_ref = f"objects/{object_store(p, canonical_bytes(proof))}"
    return proof, proof_ref


def verify_verified_candidate_proof(p: dict[str, Path], proof_ref: str) -> dict[str, Any]:
    """Re-read every immutable object named by a published candidate proof."""
    proof = stored_payload(p, proof_ref, "verified candidate proof")
    root = schema()
    validate(proof, root["$defs"]["verified_candidate_proof"], root, "$.verified_candidate_proof")
    packet = stored_payload(p, proof.get("packet_ref"), "candidate proof packet")
    returned = stored_payload(p, proof.get("return_ref"), "candidate proof worker return")
    receipt = stored_payload(p, proof.get("commit_receipt_ref"), "candidate proof commit receipt")
    audit = stored_payload(p, proof.get("write_set_audit_ref"), "candidate proof write-set audit")
    audit_hash = sha256_bytes(canonical_bytes(audit))
    if audit_hash != proof.get("write_set_audit_hash") or audit.get("pass") is not True or not audit.get("changed_paths"):
        fail("candidate proof write-set audit is missing, changed, or no longer PASS")
    if (
        receipt.get("status") != "PASS"
        or receipt.get("commit_sha") != proof.get("candidate_sha")
        or receipt.get("tree_sha") != proof.get("candidate_tree_sha")
        or receipt.get("base_sha") != proof.get("base_sha")
        or receipt.get("authority_ref") != proof.get("authority_ref")
        or not receipt.get("checkout")
        or Path(receipt["checkout"]).expanduser().resolve() != Path(proof["checkout"]).expanduser().resolve()
    ):
        fail("candidate proof commit receipt is missing or conflicts with its bound identity")
    if (
        packet.get("identity", {}).get("attempt_id") != proof.get("attempt_id")
        or proof.get("packet_ref") != f"objects/{proof.get('packet_hash')}"
        or returned.get("identity", {}).get("attempt_id") != proof.get("attempt_id")
        or returned.get("identity", {}).get("packet_hash") != proof.get("packet_hash")
    ):
        fail("candidate proof packet/return identity objects are missing or mismatched")
    if proof.get("parent_sha") != proof.get("base_sha"):
        fail("candidate proof parent SHA does not equal its exact base SHA")
    return proof


def finding_obligation_projection(state: dict[str, Any]) -> dict[str, Any]:
    """Pure current/history/resolution projection over immutable findings and their issue mirrors."""
    tickets = {item.get("id"): item for item in state.get("tickets", [])}
    attempts = {item.get("id"): item for item in state.get("attempts", [])}
    candidates = {item.get("id"): item for item in state.get("candidates", [])}
    candidates_by_attempt = {item.get("producer_attempt_ref"): item for item in state.get("candidates", [])}
    reviews = {item.get("id"): item for item in state.get("reviews", [])}
    issues = state.get("issues", [])
    issue_by_id = {item.get("id"): item for item in issues}
    design = state.get("design_publication") or {}
    design_history = state.get("design_publication_history", [])
    publications = {item.get("id"): item for item in [*design_history, design] if item.get("id")}
    effective_reconciliations: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for event in state.get("finding_binding_reconciliations", []):
        ticket = tickets.get(event.get("ticket_ref"))
        candidate = candidates.get(event.get("candidate_ref"))
        attempt = attempts.get(event.get("review_attempt_ref"))
        if (
            ticket is None or candidate is None or attempt is None
            or ticket.get("current_candidate") != candidate.get("id")
            or candidate.get("ticket_ref") != ticket.get("id")
            or candidate.get("sha") != event.get("candidate_sha")
            or candidate.get("tree_sha") != event.get("candidate_tree_sha")
            or attempt.get("kind") != "review" or attempt.get("subject_ref") != ticket.get("id")
            or attempt.get("candidate_sha") != event.get("candidate_sha")
            or attempt.get("packet_ref") != event.get("packet_ref")
            or attempt.get("packet_hash") != event.get("packet_hash")
            or attempt.get("return_ref") != event.get("return_ref")
        ):
            continue
        for binding in event.get("finding_bindings", []):
            finding = next((item for item in state.get("findings", []) if item.get("id") == binding.get("finding_ref")), None)
            issue = issue_by_id.get(binding.get("issue_ref"))
            if (
                finding is None or issue is None
                or finding.get("source_ref") != attempt.get("id")
                or issue.get("finding_ref") != finding.get("id")
                or issue.get("source_ref") != attempt.get("id")
            ):
                continue
            effective_reconciliations[finding["id"]] = (event, binding)
    accepted_pass_reviews = {
        item.get("id"): item for item in state.get("reviews", [])
        if item.get("id") and item.get("accepted") is True
        and item.get("verdict") == "PASS" and item.get("return_ref")
        and not item.get("invalidated_by")
    }
    resolutions_by_finding_ticket: dict[str, dict[str, list[str]]] = {}
    for decision in state.get("decisions", []):
        affected = decision.get("affected_refs", [])
        if (
            decision.get("type") != "finding_resolution"
            or decision.get("status") != "accepted"
            or decision.get("decision") != "RESOLVED"
            or len(affected) != 1
            or not isinstance(decision.get("reason"), str)
            or not decision.get("reason")
            or decision.get("invalidated_by")
        ):
            continue
        finding_ref = affected[0]
        candidate_ref = decision.get("candidate_ref")
        candidate = candidates.get(candidate_ref)
        finding = next((item for item in state.get("findings", []) if item.get("id") == finding_ref), None)
        review_refs = [ref for ref in decision.get("evidence_refs", []) if ref in accepted_pass_reviews]
        if candidate is None or finding is None or len(review_refs) != 1:
            continue
        review = accepted_pass_reviews[review_refs[0]]
        ticket_ref = candidate.get("ticket_ref")
        ticket = tickets.get(ticket_ref)
        if review.get("subject_fingerprint") != candidate.get("sha"):
            continue
        if (
            ticket_ref not in effective_finding_ticket_refs(state, finding_ref)
            or ticket is None
            or ticket.get("current_candidate") != candidate_ref
            or candidate.get("quality") != "DONE"
        ):
            continue
        contract = next((item for item in review.get("finding_resolution", [])
                         if item.get("finding_ref") == finding_ref
                         and item.get("candidate_ref") == candidate_ref), None)
        if contract is None:
            continue
        contract_evidence = contract.get("evidence_refs", [])
        decision_evidence = decision.get("evidence_refs", [])
        if not contract_evidence or set(decision_evidence) != {review["id"], *contract_evidence}:
            continue
        resolutions_by_finding_ticket.setdefault(finding_ref, {}).setdefault(ticket_ref, []).append(decision["id"])
    records: list[dict[str, Any]] = []
    obligations: list[dict[str, Any]] = []
    mirrors: list[dict[str, Any]] = []

    for finding in state.get("findings", []):
        finding_id = finding.get("id")
        source_id = finding.get("source_ref")
        source = attempts.get(source_id) or reviews.get(source_id)
        issue_refs = sorted(item["id"] for item in issues if item.get("finding_ref") == finding_id)
        affected_tickets = sorted(ref for ref in finding.get("affected_refs", []) if ref in tickets)
        reconciliation = effective_reconciliations.get(finding_id)
        if reconciliation is not None:
            reconciled_ticket = reconciliation[0].get("ticket_ref")
            if reconciled_ticket in tickets and reconciled_ticket not in affected_tickets:
                affected_tickets.append(reconciled_ticket)
                affected_tickets.sort()
        candidate = None
        publication = None
        source_sha = None
        if source is not None:
            source_sha = source.get("candidate_sha") or source.get("subject_fingerprint")
            if source.get("kind") == "worker" and source.get("id") in candidates_by_attempt:
                candidate = candidates_by_attempt[source["id"]]
            if candidate is None and source_sha:
                possible = [
                    item for item in state.get("candidates", [])
                    if item.get("sha") == source_sha and item.get("ticket_ref") in affected_tickets
                ]
                if len(possible) == 1:
                    candidate = possible[0]
            publication_matches = [
                item for item in publications.values()
                if source_sha and item.get("publication_hash") == source_sha
            ]
            if len(publication_matches) == 1:
                publication = publication_matches[0]

        binding_kind = None
        source_candidate_ref = None
        if candidate is not None:
            source_candidate_ref = candidate["id"]
            current_ticket = tickets.get(candidate.get("ticket_ref"), {})
            if current_ticket.get("current_candidate") == candidate.get("id"):
                binding_kind = "current"
            elif candidate.get("superseded_by"):
                binding_kind = "superseded"
            else:
                binding_kind = "historical"
        elif publication is not None:
            if publication.get("id") == design.get("id"):
                binding_kind = "current"
            elif publication.get("superseded_by") or publication.get("status") in ("SUPERSEDED", "INVALIDATED"):
                binding_kind = "superseded"
            else:
                binding_kind = "historical"
        elif reconciliation is not None:
            event = reconciliation[0]
            candidate = candidates.get(event.get("candidate_ref"))
            source_candidate_ref = candidate.get("id") if candidate else None
            binding_kind = "current"
        elif source is not None and source_sha and affected_tickets:
            # Exact attempt+ticket evidence can identify legacy history, but cannot silently
            # establish a current candidate in a ledger without the explicit Phase B pointer.
            if source.get("subject_ref") in affected_tickets:
                binding_kind = "historical"
        if binding_kind is None and source is not None and source.get("subject_ref") in publications:
            # A design review is immutably tied to its publication ID; this
            # remains exact even when a copy/rehearsal rehashes the publication
            # object and the original fingerprint no longer equals that hash.
            publication = publications[source["subject_ref"]]
            binding_kind = "current" if publication.get("id") == design.get("id") else "historical"
        if binding_kind is None and source is not None and source_sha and source.get("subject_ref") in tickets:
            # A ticket-scoped historical candidate requires both immutable source
            # attempt linkage and a candidate fingerprint. Subject linkage alone
            # is insufficient (an unbound finding may cite the same ticket).
            source_ticket = source["subject_ref"]
            if source_ticket not in affected_tickets:
                affected_tickets.append(source_ticket)
                affected_tickets.sort()
            binding_kind = "historical"

        resolutions_by_ticket = resolutions_by_finding_ticket.get(finding_id, {})
        resolved_ticket_refs = sorted(ref for ref in affected_tickets if resolutions_by_ticket.get(ref))
        unresolved_ticket_refs = sorted(set(affected_tickets) - set(resolved_ticket_refs))
        resolved_by = sorted({decision_id for ids in resolutions_by_ticket.values() for decision_id in ids})
        all_affected_tickets_resolved = bool(affected_tickets) and not unresolved_ticket_refs
        if all_affected_tickets_resolved:
            status = "resolved"
        elif binding_kind == "superseded":
            status = "superseded"
        elif binding_kind == "current":
            status = "current"
        elif binding_kind == "historical":
            status = "historical"
        else:
            status = "unbound"

        is_blocking = finding.get("impact") == "blocking"
        obligation_status = "closed" if all_affected_tickets_resolved or not is_blocking else ("binding_required" if status == "unbound" else "open")
        projection_classification = (
            "current" if status == "current" else
            "carry_forward" if status in ("historical", "superseded") and obligation_status == "open" else
            "history" if status in ("historical", "superseded", "resolved") else "unbound"
        )
        proof = finding.get("expected") or finding.get("claim") or "independent evidence that the reported defect is absent"
        item = {
            "finding_ref": finding_id,
            "status": status,
            "projection_classification": projection_classification,
            "current_applicability": status == "current",
            "repairable": status == "current" and obligation_status == "open",
            "source_candidate_ref": source_candidate_ref,
            "affected_ticket_refs": affected_tickets,
            "resolved_ticket_refs": resolved_ticket_refs,
            "unresolved_ticket_refs": unresolved_ticket_refs,
            "issue_refs": issue_refs,
            "resolved_by_refs": resolved_by,
            "verification_obligation": {
                "status": obligation_status,
                "applicability": projection_classification,
                "required_proof": proof,
                "ticket_refs": unresolved_ticket_refs,
                "issue_refs": issue_refs,
            },
        }
        records.append(item)
        if obligation_status != "closed":
            obligations.append({
                "finding_ref": finding_id,
                "status": obligation_status,
                "applicability": projection_classification,
                "required_proof": proof,
                "issue_refs": issue_refs,
                "ticket_refs": unresolved_ticket_refs,
            })
        for issue_ref in issue_refs:
            issue = issue_by_id.get(issue_ref, {})
            mirrors.append({
                "issue_ref": issue_ref,
                "finding_ref": finding_id,
                "status": status,
                "impact": issue.get("impact"),
                "active": bool(issue.get("impact") == "blocking" and obligation_status != "closed"),
                "repairable": bool(status == "current" and issue.get("impact") == "blocking" and obligation_status == "open"),
            })

    # Preserve orphan finding-typed issue obligations; missing mirrors require explicit binding.
    known_mirrors = {item["issue_ref"] for item in mirrors}
    for issue in issues:
        if issue.get("type") != "review_finding" or issue.get("id") in known_mirrors:
            continue
        mirrors.append({
            "issue_ref": issue.get("id"), "finding_ref": issue.get("finding_ref"),
            "status": "unbound", "impact": issue.get("impact"),
            "active": issue.get("impact") == "blocking" and not issue.get("invalidated_by"),
            "repairable": False,
        })
        if issue.get("impact") == "blocking" and not issue.get("invalidated_by"):
            obligations.append({
                "finding_ref": issue.get("finding_ref"), "issue_ref": issue.get("id"),
                "status": "binding_required", "applicability": "unbound",
                "required_proof": issue.get("resolution_condition") or issue.get("expected") or "bind issue to a canonical finding and verification evidence",
                "issue_refs": [issue.get("id")], "ticket_refs": sorted(ref for ref in issue.get("affected_refs", []) if ref in tickets),
            })
    known_issue_refs = {item.get("issue_ref") for item in mirrors}
    for issue in issues:
        if issue.get("id") in known_issue_refs:
            continue
        issue_status = "superseded" if issue.get("invalidated_by") else "current"
        mirrors.append({
            "issue_ref": issue.get("id"),
            "finding_ref": issue.get("finding_ref") or issue.get("id"),
            "status": issue_status,
            "impact": issue.get("impact"),
            "active": bool(issue.get("impact") == "blocking" and not issue.get("invalidated_by")),
            "repairable": bool(issue_status == "current" and issue.get("impact") == "blocking" and not issue.get("invalidated_by")),
        })
    return {
        "items": records, "obligations": obligations, "mirrored_issues": mirrors,
        "current_finding_refs": sorted(item["finding_ref"] for item in records if item["projection_classification"] == "current"),
        "historical_finding_refs": sorted(item["finding_ref"] for item in records if item["projection_classification"] == "history"),
        "carry_forward_finding_refs": sorted(item["finding_ref"] for item in records if item["projection_classification"] == "carry_forward"),
    }


def _validate_review05_reconciliation(
    state: dict[str, Any], source_raw: bytes, manifest: dict[str, Any],
    payload_loader: Callable[[str, str], tuple[dict[str, Any], bytes]],
) -> dict[str, Any]:
    root = schema()
    validate(manifest, root["$defs"]["finding_binding_reconciliation_manifest"], root, "$.finding_binding_manifest")
    source_hash = sha256_bytes(source_raw)
    exact = {
        "source_revision": state.get("revision"),
        "source_ledger_hash": source_hash,
        "owner_epoch": state.get("owner", {}).get("epoch"),
        "review_attempt_ref": "T02-R17-REVIEW-CODE-05",
        "ticket_ref": "T02-R17",
    }
    for field, value in exact.items():
        if manifest.get(field) != value:
            fail(f"finding binding manifest {field} does not match the exact current source")
    ticket = next((item for item in state.get("tickets", []) if item.get("id") == manifest["ticket_ref"]), None)
    attempt = next((item for item in state.get("attempts", []) if item.get("id") == manifest["review_attempt_ref"]), None)
    worker = next((item for item in state.get("attempts", []) if item.get("id") == "T02-R17-WORKER-05"), None)
    candidate = next((item for item in state.get("candidates", []) if item.get("id") == manifest.get("candidate_ref")), None)
    if (
        ticket is None or attempt is None or worker is None
        or ticket.get("id") not in (state.get("design_publication") or {}).get("ticket_refs", [])
        or attempt.get("kind") != "review" or attempt.get("state") != "RETURNED"
        or attempt.get("lease", {}).get("state") != "released"
        or attempt.get("subject_ref") != ticket.get("id")
        or attempt.get("review_result") != "BLOCK"
        or worker.get("kind") != "worker" or worker.get("subject_ref") != ticket.get("id")
        or worker.get("state") != "RETURNED" or ticket.get("current_attempt") != worker.get("id")
        or attempt.get("candidate_sha") != manifest.get("candidate_sha")
        or attempt.get("subject_fingerprint") != manifest.get("candidate_sha")
        or worker.get("candidate_sha") != manifest.get("candidate_sha")
        or worker.get("candidate_tree_sha") != manifest.get("candidate_tree_sha")
        or worker.get("continuation_ref") != manifest.get("continuation_receipt_ref")
        or candidate is None or ticket.get("current_candidate") != candidate.get("id")
        or candidate.get("producer_attempt_ref") != worker.get("id")
        or candidate.get("quality") != "CONTINUATION"
        or candidate.get("sha") != manifest.get("candidate_sha")
        or candidate.get("tree_sha") != manifest.get("candidate_tree_sha")
    ):
        fail("Review05 manifest is not bound to the registered ticket and exact current continuation candidate")
    candidate_id = f"candidate-{worker['id']}"
    if manifest.get("candidate_ref") != candidate_id:
        fail("Review05 manifest candidate_ref is not the durable current continuation candidate ID")

    expected_refs = {
        "packet_ref": attempt.get("packet_ref"), "packet_hash": attempt.get("packet_hash"),
        "return_ref": attempt.get("return_ref"),
        "continuation_receipt_ref": worker.get("continuation_ref"),
    }
    for field, value in expected_refs.items():
        if manifest.get(field) != value:
            fail(f"Review05 manifest {field} does not match exact ledger binding")
    for ref_field, hash_field in (("packet_ref", "packet_hash"), ("return_ref", "return_hash"), ("continuation_receipt_ref", "continuation_receipt_hash")):
        if manifest[ref_field] != f"objects/{manifest[hash_field]}":
            fail(f"Review05 manifest {ref_field}/{hash_field} pair is inconsistent")

    packet, packet_raw = payload_loader(manifest["packet_ref"], "Review05 packet")
    returned, return_raw = payload_loader(manifest["return_ref"], "Review05 return")
    continuation, continuation_raw = payload_loader(manifest["continuation_receipt_ref"], "Worker05 continuation receipt")
    if sha256_bytes(packet_raw) != manifest["packet_hash"] or sha256_bytes(return_raw) != manifest["return_hash"] or sha256_bytes(continuation_raw) != manifest["continuation_receipt_hash"]:
        fail("Review05 packet, return, or continuation receipt bytes do not match exact manifest hashes")
    packet_identity_value = packet.get("identity", {})
    return_identity = returned.get("identity", {})
    if (
        packet_identity_value.get("run_id") != state.get("run_id")
        or packet_identity_value.get("ticket_id") != ticket.get("id")
        or packet_identity_value.get("attempt_id") != attempt.get("id")
        or return_identity.get("run_id") != state.get("run_id")
        or return_identity.get("ticket_id") != ticket.get("id")
        or return_identity.get("attempt_id") != attempt.get("id")
        or return_identity.get("packet_hash") != manifest.get("packet_hash")
        or returned.get("verdict") != "BLOCK"
        or continuation.get("attempt_id") != worker.get("id")
        or continuation.get("candidate_sha") != manifest.get("candidate_sha")
        or continuation.get("candidate_tree_sha") != manifest.get("candidate_tree_sha")
        or continuation.get("base_sha") != worker.get("base_sha")
        or continuation.get("blocker_scope") != "external"
    ):
        fail("Review05 immutable payloads do not prove the exact ticket/attempt/candidate/blocker identity")
    external_blocker_ref = continuation.get("blocker_ref")
    external_blocker = next((item for item in state.get("issues", []) if item.get("id") == external_blocker_ref), None)
    if (
        external_blocker is None or external_blocker.get("impact") != "blocking"
        or external_blocker.get("invalidated_by")
        or external_blocker_ref not in candidate.get("blocker_refs", [])
    ):
        fail("Review05 continuation receipt does not identify its still-current registered external blocker")

    return_findings = returned.get("findings", [])
    source_findings = [item for item in state.get("findings", []) if item.get("source_ref") == attempt.get("id")]
    if len(return_findings) != 3 or len(source_findings) != 3:
        fail("Review05 recovery requires exactly three immutable return findings and ledger findings")
    source_by_signature: dict[bytes, dict[str, Any]] = {}
    compared_fields = ("axis", "impact", "claim", "expected", "actual", "evidence")
    for finding in source_findings:
        source_by_signature[canonical_bytes({key: finding.get(key) for key in compared_fields})] = finding
    matched_finding_refs: set[str] = set()
    for returned_finding in return_findings:
        signature = canonical_bytes({key: returned_finding.get(key) for key in compared_fields})
        matched = source_by_signature.get(signature)
        if matched is None:
            fail("Review05 raw finding content differs from its exact immutable ledger finding")
        if matched.get("reported_affected_refs") != returned_finding.get("affected_refs"):
            fail("Review05 reported_affected_refs differ from the exact immutable return order/content")
        if set(matched.get("affected_refs", [])) != set(returned_finding.get("affected_refs", [])):
            fail("Review05 normalized finding affected_refs differ from the exact returned reference set")
        matched_finding_refs.add(matched["id"])
    if set(attempt.get("finding_refs", [])) != matched_finding_refs:
        fail("Review05 attempt finding_refs do not match exactly the three returned findings")
    issues = [item for item in state.get("issues", []) if item.get("finding_ref") in matched_finding_refs]
    issue_by_finding: dict[str, list[dict[str, Any]]] = {}
    for issue in issues:
        issue_by_finding.setdefault(issue.get("finding_ref"), []).append(issue)
    if set(issue_by_finding) != matched_finding_refs or any(len(values) != 1 for values in issue_by_finding.values()):
        fail("Review05 recovery requires exactly one existing mirrored issue for each of its three findings")
    findings_by_id = {item.get("id"): item for item in source_findings}
    ticket_contract_refs = set(ticket.get("contract_refs", []))
    publication_contract_refs = set((state.get("design_publication") or {}).get("contract_refs", []))
    for finding_ref, values in issue_by_finding.items():
        issue = values[0]
        finding = findings_by_id[finding_ref]
        if (
            issue.get("source_ref") != attempt.get("id")
            or issue.get("impact") != "blocking" or issue.get("invalidated_by")
            or finding.get("impact") != "blocking" or finding.get("invalidated_by")
            or set(issue.get("affected_refs", [])) != set(finding.get("affected_refs", []))
            or not ((ticket_contract_refs | publication_contract_refs) & set(issue.get("affected_refs", [])))
        ):
            fail("Review05 finding issue mirror is stale or has incompatible blocking/affected context")
    expected_bindings = sorted(
        ({"finding_ref": finding_ref, "issue_ref": values[0]["id"]} for finding_ref, values in issue_by_finding.items()),
        key=lambda item: (item["finding_ref"], item["issue_ref"]),
    )
    supplied_bindings = sorted(manifest.get("finding_bindings", []), key=lambda item: (item["finding_ref"], item["issue_ref"]))
    if supplied_bindings != expected_bindings:
        fail("Review05 manifest finding_bindings must exactly match the three existing finding/issue mirrors")

    return {
        "source_revision": state["revision"], "source_ledger_hash": source_hash,
        "owner_epoch": manifest["owner_epoch"], "review_attempt_ref": attempt["id"],
        "ticket_ref": ticket["id"], "candidate_ref": candidate_id,
        "candidate_sha": worker["candidate_sha"], "candidate_tree_sha": worker["candidate_tree_sha"],
        "packet_ref": attempt["packet_ref"], "packet_hash": attempt["packet_hash"],
        "return_ref": attempt["return_ref"], "return_hash": manifest["return_hash"],
        "continuation_receipt_ref": worker["continuation_ref"],
        "continuation_receipt_hash": manifest["continuation_receipt_hash"],
        "finding_bindings": expected_bindings,
    }


def _stored_payload_with_bytes(p: dict[str, Path], ref: str, label: str) -> tuple[dict[str, Any], bytes]:
    payload = stored_payload(p, ref, label)
    match = re.fullmatch(r"objects/([0-9a-f]{64})", ref)
    if match is None:
        fail(f"{label} is not an immutable object reference")
    raw = (p["objects"] / match.group(1)).read_bytes()
    return payload, raw


def _cmd_reconcile_finding_bindings(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    manifest, manifest_raw = _read_manifest(args.manifest, "finding binding reconciliation manifest")
    root = schema()
    validate(manifest, root["$defs"]["finding_binding_reconciliation_manifest"], root, "$.finding_binding_manifest")
    manifest_hash = sha256_bytes(manifest_raw)
    with Lock(p["lock"]):
        state, raw = load_state(p)
        if state.get("owner", {}).get("token") != args.owner_token:
            fail("owner token mismatch; stale orchestrator is fenced")
        prior = next((item for item in state.get("finding_binding_reconciliations", []) if item.get("reconciliation_id") == manifest.get("reconciliation_id")), None)
        if prior is not None:
            if prior.get("manifest_hash") == manifest_hash and prior.get("source_ledger_hash") == manifest.get("source_ledger_hash") and prior.get("source_revision") == manifest.get("source_revision"):
                if args.revision not in {manifest.get("source_revision"), prior.get("applied_revision"), state.get("revision")}:
                    fail(f"revision mismatch on reconciliation replay: expected source/applied/current revision, got {args.revision}")
                return {"reconciled": True, "idempotent": True, "reconciliation_id": manifest["reconciliation_id"], "manifest_hash": manifest_hash, "applied_revision": prior.get("applied_revision"), "finding_refs": [item["finding_ref"] for item in prior.get("finding_bindings", [])], "issue_refs": [item["issue_ref"] for item in prior.get("finding_bindings", [])]}
            fail("finding reconciliation ID already exists with conflicting manifest/source")
        if state.get("revision") != args.revision:
            fail(f"revision mismatch: expected {args.revision}, current {state.get('revision')}")
        require_mutation_eligible(state)
        if manifest.get("source_revision") != args.revision or manifest.get("source_ledger_hash") != sha256_bytes(raw):
            fail("finding binding manifest must bind the exact current ledger revision and hash")
        if manifest.get("owner_epoch") != state.get("owner", {}).get("epoch"):
            fail("finding binding manifest owner_epoch does not match current owner epoch")
        record_fields = _validate_review05_reconciliation(
            state, raw, manifest, lambda ref, label: _stored_payload_with_bytes(p, ref, label),
        )
        for event in state.get("finding_binding_reconciliations", []):
            if event.get("review_attempt_ref") == record_fields["review_attempt_ref"] or any(
                binding.get("finding_ref") in {item["finding_ref"] for item in record_fields["finding_bindings"]}
                for binding in event.get("finding_bindings", [])
            ):
                fail("conflicting finding binding reconciliation already exists")
        event_id = f"finding-binding-reconciliation-{manifest['reconciliation_id']}"
        applied_revision = state["revision"] + 1
        manifest_digest = object_store(p, manifest_raw)
        event = {
            "id": event_id, "reconciliation_id": manifest["reconciliation_id"],
            **record_fields, "manifest_hash": manifest_hash,
            "manifest_ref": f"objects/{manifest_digest}",
            "applied_revision": applied_revision, "recorded_at": now(),
        }
        state.setdefault("finding_binding_reconciliations", []).append(event)
        state["revision"] = applied_revision
        state["previous_publication_hash"] = sha256_bytes(raw)
        state["updated_at"] = now()
        ensure_runtime_provenance(state)
        refresh_control_projection(state)
        validate_ledger(state, verify_files=False)
        publish(p, state, raw, "finding-binding-reconciliation")
        return {"reconciled": True, "idempotent": False, "reconciliation_id": manifest["reconciliation_id"], "manifest_hash": manifest_hash, "applied_revision": applied_revision, "finding_refs": [item["finding_ref"] for item in record_fields["finding_bindings"]], "issue_refs": [item["issue_ref"] for item in record_fields["finding_bindings"]]}


def _fixture_payload_loader(source_file: Path) -> Callable[[str, str], tuple[dict[str, Any], bytes]]:
    fixture_files = {
        "review05-packet.json": "packet",
        "review05-return.json": "return",
        "worker05-continuation-receipt.json": "continuation",
    }
    def load(ref: str, label: str) -> tuple[dict[str, Any], bytes]:
        expected_name = next((name for name in fixture_files if (
            name.startswith("review05-packet") and "packet" in label.lower()
            or name.startswith("review05-return") and "return" in label.lower()
            or name.startswith("worker05-continuation") and "continuation" in label.lower()
        )), None)
        if expected_name is None:
            fail(f"no frozen R58 fixture artifact is defined for {label}")
        target = source_file.parent / expected_name
        regular_non_symlink(target)
        raw = target.read_bytes()
        digest = sha256_bytes(raw)
        if ref != f"objects/{digest}":
            fail(f"frozen R58 {label} bytes do not match the exact immutable reference")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            fail(f"frozen R58 {label} is not valid JSON: {exc}")
        if not isinstance(payload, dict):
            fail(f"frozen R58 {label} must be a JSON object")
        return payload, raw
    return load


def _cmd_rehearse_legacy_recovery(args: argparse.Namespace) -> dict[str, Any]:
    source_file = Path(args.file).expanduser()
    regular_non_symlink(source_file)
    source_raw = source_file.read_bytes()
    try:
        source_state = json.loads(source_raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        fail(f"legacy source ledger is not valid UTF-8 JSON: {exc}")
    if not isinstance(source_state, dict):
        fail("legacy source ledger must be a JSON object")
    validate_ledger(source_state, verify_files=False)
    binding_manifest, _ = _read_manifest(args.binding_manifest, "binding normalization manifest")
    finding_manifest, _ = _read_manifest(args.finding_manifest, "finding binding reconciliation manifest")
    assessment = assess_legacy_binding_manifest(source_state, source_raw, binding_manifest)
    if not assessment.get("migration_eligible"):
        fail("R58 rehearsal cannot normalize material or ambiguous bindings; owner must replan affected G2/G3")

    rehearsal = copy.deepcopy(source_state)
    loader = _fixture_payload_loader(source_file)
    # Bootstrap only into the in-memory copy; raw source ticket/findings/publication records remain untouched.
    continuation, _continuation_raw = loader(
        next((item.get("continuation_receipt_ref") for item in [finding_manifest] if item), ""),
        "Worker05 continuation receipt",
    )
    _bootstrap_legacy_candidate_model_from_receipt(rehearsal, continuation)
    finding_fields = _validate_review05_reconciliation(rehearsal, source_raw, finding_manifest, loader)
    effective_bindings = []
    for item in assessment["intersections"]:
        normalized = copy.deepcopy(item)
        normalized["implementation_availability"] = "not_required"
        effective_bindings.append(normalized)
    rehearsal.setdefault("binding_normalizations", []).append({
        "id": "rehearsal-binding-normalization", "migration_id": binding_manifest["migration_id"],
        "source_revision": assessment["source_revision"], "source_ledger_hash": assessment["source_ledger_hash"],
        "publication_ref": assessment["publication_ref"], "publication_hash": assessment["publication_hash"],
        "manifest_hash": sha256_bytes(canonical_bytes(binding_manifest)), "manifest_ref": "objects/" + "0" * 64,
        "owner_epoch": binding_manifest["owner_epoch"], "applied_revision": source_state["revision"] + 1,
        "bindings": effective_bindings, "recorded_at": "rehearsal",
    })
    rehearsal.setdefault("finding_binding_reconciliations", []).append({
        "id": "rehearsal-finding-binding", "reconciliation_id": finding_manifest["reconciliation_id"],
        **finding_fields, "manifest_hash": sha256_bytes(canonical_bytes(finding_manifest)),
        "manifest_ref": "objects/" + "0" * 64,
        "applied_revision": source_state["revision"] + 1, "recorded_at": "rehearsal",
    })
    projection = finding_obligation_projection(rehearsal)
    finding_by_id = {item.get("id"): item for item in rehearsal.get("findings", [])}
    ticket_findings = [
        item for item in source_state.get("findings", [])
        if (attempt := next((row for row in source_state.get("attempts", []) if row.get("id") == item.get("source_ref")), None))
        and attempt.get("subject_ref") == "T02-R17"
        and attempt.get("id") != "T02-R17-REVIEW-CODE-05"
    ]
    historical_ticket_count = sum(
        1 for finding in ticket_findings
        if next((row for row in projection["items"] if row["finding_ref"] == finding["id"]), {}).get("projection_classification") in ("history", "carry_forward")
    )
    historical_design_count = sum(
        1 for finding in source_state.get("findings", [])
        if (attempt := next((row for row in source_state.get("attempts", []) if row.get("id") == finding.get("source_ref")), None))
        and attempt.get("kind") == "review" and attempt.get("mode") in ("coverage", "plan")
        and next((row for row in projection["items"] if row["finding_ref"] == finding["id"]), {}).get("projection_classification") in ("history", "carry_forward")
    )
    external_blocker_ref = continuation.get("blocker_ref")
    external_blocker = next((item for item in source_state.get("issues", []) if item.get("id") == external_blocker_ref), None)
    if external_blocker is None or external_blocker.get("invalidated_by"):
        fail("R58 rehearsal must retain the exact current external continuation blocker")
    if len(projection["current_finding_refs"]) != 3:
        fail("R58 rehearsal did not produce exactly three current Review05 findings")
    return {
        "read_only": True,
        "source_hash_unchanged": sha256_bytes(source_file.read_bytes()) == sha256_bytes(source_raw),
        "source_revision": source_state["revision"],
        "source_ledger_hash": sha256_bytes(source_raw),
        "intersection_count": assessment["intersection_count"],
        "current_finding_count": len(projection["current_finding_refs"]),
        "historical_ticket_finding_count": historical_ticket_count,
        "historical_design_finding_count": historical_design_count,
        "external_blocker_ref": external_blocker_ref,
        "next_action": "authorize bounded repair for the three current Review05 findings; retain historical obligations and external blocker",
        "finding_projection": projection,
    }


def _bootstrap_legacy_candidate_model_from_receipt(state: dict[str, Any], receipt: dict[str, Any]) -> None:
    """In-memory counterpart of the exact R58 candidate bootstrap used by rehearsal."""
    if state.get("candidate_model_version") == "1.1":
        return
    if state.get("candidates") or any(ticket.get("current_candidate") for ticket in state.get("tickets", [])):
        fail("legacy candidate bootstrap is ambiguous: candidate records or pointers already exist")
    ticket = next((item for item in state.get("tickets", []) if item.get("id") == "T02-R17"), None)
    worker = next((item for item in state.get("attempts", []) if item.get("id") == "T02-R17-WORKER-05"), None)
    if (
        ticket is None or ticket.get("state") != "BLOCKED" or worker is None
        or worker.get("state") != "RETURNED" or ticket.get("current_attempt") != worker.get("id")
        or receipt.get("attempt_id") != worker.get("id")
        or receipt.get("candidate_sha") != worker.get("candidate_sha")
        or receipt.get("candidate_tree_sha") != worker.get("candidate_tree_sha")
        or receipt.get("base_sha") != worker.get("base_sha")
    ):
        fail("frozen R58 continuation receipt cannot conservatively bootstrap the current candidate")
    blocker_ref = receipt.get("blocker_ref")
    if receipt.get("blocker_scope") != "external" or not any(item.get("id") == blocker_ref for item in state.get("issues", [])):
        fail("frozen R58 continuation candidate is missing its exact external blocker")
    candidate_id = f"candidate-{worker['id']}"
    state.setdefault("candidates", []).append({
        "id": candidate_id, "ticket_ref": ticket["id"], "sha": worker["candidate_sha"],
        "tree_sha": worker["candidate_tree_sha"], "base_sha": worker.get("base_sha"),
        "producer_attempt_ref": worker["id"], "parent_candidate_ref": None,
        "quality": "CONTINUATION", "blocker_refs": [blocker_ref],
        "review_status": "BLOCK", "integration_status": "PENDING",
    })
    attempts_by_id = {item.get("id"): item for item in state.get("attempts", [])}
    for item in state.get("tickets", []):
        prior = attempts_by_id.get(item.get("current_attempt"))
        workers = [attempt for attempt in state.get("attempts", []) if attempt.get("kind") == "worker" and attempt.get("subject_ref") == item.get("id")]
        last = prior if prior and prior.get("kind") == "worker" else (max(workers, key=lambda attempt: attempt.get("attempt_created_revision", -1)) if workers else None)
        item["last_worker_attempt"] = last.get("id") if last else None
        item["current_attempt"] = item["last_worker_attempt"]
        item["current_worker_attempt"] = item["last_worker_attempt"] if last and last.get("state") in ("PREPARED", "DISPATCHED") else None
        item["current_candidate"] = None
    ticket["current_candidate"] = candidate_id
    state["candidate_model_version"] = "1.1"
    state["review_model_version"] = "1.1"
    state.setdefault("review_qualifications", [])
    state.setdefault("repair_waves", [])
    state.setdefault("acceptance", [])


def open_ticket_finding_obligations(state: dict[str, Any], ticket_id: str) -> list[dict[str, Any]]:
    """Return the shared unresolved verification-obligation view for one ticket."""
    projection = finding_obligation_projection(state)
    return [
        item for item in projection["obligations"]
        if ticket_id in item.get("ticket_refs", []) and item.get("status") != "closed"
    ]


def _blocked_repair_review_integrate_ready(state: dict[str, Any]) -> bool:
    """Admit BLOCKED integration only with a current DONE candidate and exact review attempt."""
    lifecycle = state.get("lifecycle", {})
    if lifecycle.get("control") != "BLOCKED" or lifecycle.get("phase") != "EXECUTE":
        return False
    attempts = [item for item in state.get("attempts", []) if isinstance(item, dict)]
    for ticket in state.get("tickets", []):
        candidate = current_candidate_record(state, ticket)
        if (
            candidate is None
            or candidate.get("quality") != "DONE"
            or candidate.get("review_status") == "BLOCK"
            or candidate.get("integration_status") == "INTEGRATED"
        ):
            continue
        if any(
            attempt.get("kind") == "review"
            and attempt.get("subject_ref") == ticket.get("id")
            and attempt.get("candidate_sha") == candidate.get("sha")
            and attempt.get("subject_fingerprint") == candidate.get("sha")
            and attempt.get("state") in ("PREPARED", "RETURNED")
            and (attempt.get("state") != "RETURNED" or attempt.get("review_result") == "PASS")
            and not attempt.get("invalidated_by")
            for attempt in attempts
        ):
            return True
    return False


def repair_candidate_worker(
    state: dict[str, Any], ticket: dict[str, Any], repair: dict[str, Any], packet_base: str
) -> dict[str, Any]:
    """Resolve the one current worker candidate authorized for this repair base."""
    source_ref = repair.get("source_attempt_ref")
    current = current_candidate_producer(state, ticket)
    if (
        current is None
        or current.get("kind") != "worker"
        or current.get("subject_ref") != ticket["id"]
        or current.get("candidate_sha") != packet_base
    ):
        fail("repair lease expansion base SHA is stale or forked from the current ticket candidate")
    source = next((item for item in state.get("attempts", []) if item.get("id") == source_ref), None) if source_ref else current
    if source is None or source.get("subject_ref") != ticket["id"]:
        fail("repair lease expansion requires exact same-ticket source_attempt_ref provenance")
    if source.get("kind") == "worker":
        if source.get("id") != current.get("id"):
            fail("repair lease expansion source worker is stale or forked from the current ticket candidate")
    elif source.get("kind") == "review":
        refs = repair_finding_refs(repair)
        if (
            source.get("candidate_sha") != packet_base
            or source.get("subject_fingerprint") not in (None, packet_base)
        ):
            fail("repair lease expansion source review is not the exact candidate-bound finding review")
        if any(
            ref not in source.get("finding_refs", [])
            or not any(item.get("id") == ref and item.get("source_ref") == source.get("id") for item in state.get("findings", []))
            for ref in refs
        ):
            fail("repair lease expansion source review is not the exact candidate-bound finding review")
    else:
        fail("repair lease expansion source_attempt_ref must name the current worker or its finding review")
    return current


def repair_requires_transitive_create_modify_provenance(
    p: dict[str, Path], state: dict[str, Any], ticket: dict[str, Any]
) -> bool:
    """Detect a repair of a current candidate that crosses a create-only zone."""
    current = current_candidate_producer(state, ticket)
    if (
        current is None
        or current.get("kind") != "worker"
        or current.get("subject_ref") != ticket.get("id")
        or current.get("state") != "RETURNED"
        or not current.get("candidate_sha")
        or not current.get("return_ref")
    ):
        return False

    returned = validated_candidate_worker_return(p, state, ticket, current)

    candidate_paths = {
        relative_path(item.get("path"), "current candidate return path")
        for item in returned.get("files", [])
        if item.get("operation") in ("create", "modify")
    }
    provenance = current.get("repair_lease_provenance")
    if isinstance(provenance, dict):
        candidate_paths.update(
            relative_path(item.get("path"), "current repair provenance path")
            for item in provenance.get("expanded_entries", [])
        )
    return any(
        zone_allows(ticket.get("zone", []), path, "create")
        and not zone_allows(ticket.get("zone", []), path, "modify")
        for path in candidate_paths
    )


def historical_repair_authorization(
    p: dict[str, Path], state: dict[str, Any], ticket_id: str, attempt: dict[str, Any], candidate_sha: str
) -> tuple[str, str]:
    """Revalidate one already-consumed repair authorization in a lineage."""
    repair = attempt.get("repair_contract")
    authorization_ref = attempt.get("repair_authorization_ref")
    provenance = attempt.get("repair_lease_provenance")
    if not isinstance(repair, dict):
        fail("repair lineage contains a repair attempt without a repair contract")
    finding_refs = repair_finding_refs(repair)
    finding_ref = finding_refs[0] if finding_refs else None
    authorization = next(
        (
            item
            for item in state.get("decisions", [])
            if item.get("id") == authorization_ref
            and item.get("type") == "repair_authorization"
            and item.get("status") in ("authorized", "consumed")
            and item.get("decision") == "REPAIR"
            and ticket_id in item.get("affected_refs", [])
            and set(finding_refs).issubset(set(item.get("affected_refs", [])))
            and (item.get("status") == "authorized" or item.get("consumed_by") == attempt.get("id"))
            and not item.get("invalidated_by")
        ),
        None,
    )
    if authorization is None:
        fail("repair lineage contains a repair without an accepted same-ticket authorization")
    if isinstance(provenance, dict) and (
        provenance.get("authorization_ref") != authorization_ref
        or provenance.get("finding_ref") != finding_ref
    ):
        fail("repair lineage authorization/finding provenance is discontinuous")
    repair_plan_ref = authorization.get("repair_plan_ref")
    authorized_plan = stored_payload(p, repair_plan_ref, "lineage RepairPlan") if repair_plan_ref else None
    canonical_fields = {
        "cause": repair.get("cause"),
        "finding_refs": sorted(finding_refs),
        "finding_proofs": sorted(repair_proofs(repair), key=lambda item: item["finding_ref"]),
        "stopping_condition": repair.get("stopping_condition"),
        "causal_change": repair.get("causal_change"),
        "source_attempt_ref": repair.get("source_attempt_ref"),
    }
    contract_bound = bool(
        authorized_plan
        and attempt.get("repair_plan_ref") == repair_plan_ref
        and {key: authorized_plan.get(key) for key in canonical_fields} == canonical_fields
        and authorized_plan.get("source_candidate_sha") == attempt.get("base_sha")
    )
    if not repair_plan_ref:
        legacy_refs = [ref for ref in authorization.get("evidence_refs", []) if isinstance(ref, str) and ref.startswith("objects/")]
        contract_bound = len(legacy_refs) == 1 and stored_payload(p, legacy_refs[0], "legacy lineage repair contract") == repair
    if not contract_bound and attempt.get("quarantine_reconciliation_ref"):
        receipt = stored_payload(p, attempt.get("quarantine_reconciliation_ref"), "lineage reconciliation receipt")
        receipt_contract_ref = receipt.get("repair_contract_ref")
        contract_bound = bool(
            receipt.get("authorization_ref") == authorization_ref
            and receipt.get("finding_ref") == finding_ref
            and stored_payload(p, receipt_contract_ref, "lineage reconciled repair contract") == repair
        )
    if not contract_bound:
        fail("repair lineage authorization is not bound to the exact repair contract")
    finding = next((item for item in state.get("findings", []) if item.get("id") == finding_ref), None)
    source_review = next(
        (
            item
            for item in state.get("attempts", [])
            if finding is not None and item.get("id") == finding.get("source_ref")
        ),
        None,
    )
    historical_candidate_binding = bool(
        finding
        and finding.get("impact") == "blocking"
        and source_review
        and source_review.get("kind") == "review"
        and source_review.get("subject_ref") == ticket_id
        and source_review.get("state") == "RETURNED"
        and source_review.get("candidate_sha") == candidate_sha
        and source_review.get("subject_fingerprint") in (None, candidate_sha)
        and finding_ref in source_review.get("finding_refs", [])
    )
    if not finding_matches_candidate(state, finding_ref, ticket_id, candidate_sha) and not historical_candidate_binding:
        fail("repair lineage finding is not a current blocking finding bound to its base candidate")
    return authorization_ref, finding_ref


def validated_repair_path_lineage(
    p: dict[str, Path],
    state: dict[str, Any],
    ticket: dict[str, Any],
    source_attempt: dict[str, Any],
    path: str,
    expected_candidate: str,
    seen: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Prove a continuous same-ticket candidate chain back to one validated create."""
    seen = set() if seen is None else set(seen)
    attempt_id = source_attempt.get("id")
    if attempt_id in seen:
        fail("repair lineage contains a provenance cycle")
    seen.add(attempt_id)
    if (
        source_attempt.get("kind") != "worker"
        or source_attempt.get("subject_ref") != ticket["id"]
        or source_attempt.get("state") != "RETURNED"
        or source_attempt.get("candidate_sha") != expected_candidate
        or source_attempt.get("lease", {}).get("state") == "quarantined"
    ):
        fail("repair lineage candidate is missing, foreign, stale, or quarantined")
    returned = validated_candidate_worker_return(p, state, ticket, source_attempt)
    operations = {
        item.get("operation")
        for item in returned.get("files", [])
        if relative_path(item.get("path"), "repair lineage return path") == path
    }
    base_entry = {
        "attempt_ref": attempt_id,
        "ticket_ref": ticket["id"],
        "base_sha": source_attempt.get("base_sha"),
        "candidate_sha": source_attempt.get("candidate_sha"),
        "return_ref": source_attempt.get("return_ref"),
    }
    if operations == {"create"}:
        if (
            source_attempt.get("mode") != "implement"
            or not zone_allows(ticket.get("zone", []), path, "create")
            or not zone_allows(source_attempt.get("lease", {}).get("zone", []), path, "create")
        ):
            fail(f"repair lineage lacks an original validated same-ticket create: {path}")
        return [{**base_entry, "operation": "create"}]
    if operations not in (set(), {"modify"}) or source_attempt.get("mode") != "repair":
        fail(f"repair lineage does not continuously reach an original validated create: {path}")
    provenance = source_attempt.get("repair_lease_provenance")
    base_sha = source_attempt.get("base_sha")
    authorization_ref, finding_ref = historical_repair_authorization(
        p, state, ticket["id"], source_attempt, base_sha
    )
    if isinstance(provenance, dict):
        if provenance.get("packet_base_sha") != base_sha or provenance.get("candidate_sha") != base_sha:
            fail(f"repair lineage has a broken create-to-modify provenance edge: {path}")
        prior_ref = provenance.get("source_attempt_ref")
        prior = next((item for item in state.get("attempts", []) if item.get("id") == prior_ref), None)
    else:
        prior_candidates = [
            item
            for item in state.get("attempts", [])
            if item.get("kind") == "worker"
            and item.get("subject_ref") == ticket["id"]
            and item.get("candidate_sha") == base_sha
            and item.get("id") != attempt_id
        ]
        if len(prior_candidates) != 1:
            fail("repair lineage candidate/base SHA chain is missing, ambiguous, or forked")
        prior = prior_candidates[0]
    if operations == {"modify"} and (
        not isinstance(provenance, dict)
        or not zone_allows(provenance.get("expanded_entries", []), path, "modify")
        or not zone_allows(source_attempt.get("lease", {}).get("zone", []), path, "modify")
    ):
        fail(f"repair lineage has a broken create-to-modify provenance edge: {path}")
    if prior is None or prior.get("candidate_sha") != base_sha:
        fail("repair lineage candidate/base SHA chain is stale or forked")
    lineage = validated_repair_path_lineage(p, state, ticket, prior, path, base_sha, seen)
    lineage.append(
        {
            **base_entry,
            "operation": "modify" if operations else "preserve",
            "authorization_ref": authorization_ref,
            "finding_ref": finding_ref,
        }
    )
    return lineage


def effective_worker_lease(
    p: dict[str, Path], state: dict[str, Any], ticket: dict[str, Any], packet: dict[str, Any],
    *, authorization_override: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Derive a packet-scoped lease, with one provenance-bound repair exception."""
    requested = packet_write_zone(packet)
    ticket_zone = ticket.get("zone", [])
    repair = packet.get("repair") if packet.get("mode") == "repair" else None
    finding_refs = repair_finding_refs(repair) if repair else []
    finding_ref = finding_refs[0] if finding_refs else None
    authorization = validate_repair_authorization(
        p, state, ticket["id"], repair, authorization_override=authorization_override
    ) if repair else None
    denied = [relative_path(item, "packet write deny path").rstrip("/") for item in packet.get("write", {}).get("deny", [])]
    deny_conflicts = [
        {"path": entry["path"], "denied": denied_path}
        for entry in requested for denied_path in denied
        if entry["path"] == denied_path or entry["path"].startswith(denied_path + "/") or denied_path.startswith(entry["path"] + "/")
    ]
    if deny_conflicts:
        fail(f"packet write allowlist conflicts with deny list: {json.dumps(deny_conflicts, sort_keys=True)}")

    disallowed = [
        {"path": entry["path"], "operation": operation}
        for entry in requested
        for operation in entry["operations"]
        if not zone_allows(ticket_zone, entry["path"], operation)
    ]
    if not disallowed:
        return requested, None
    if not repair:
        fail(f"packet write allowlist exceeds the ticket zone: {json.dumps(disallowed, sort_keys=True)}")

    packet_base = packet.get("workspace", {}).get("expected_base")
    source_attempt = repair_candidate_worker(state, ticket, repair, packet_base)
    source_attempt_ref = source_attempt["id"]
    if source_attempt.get("state") != "RETURNED" or not source_attempt.get("return_ref") or not source_attempt.get("candidate_sha"):
        fail("repair lease expansion requires a validated prior candidate attempt")
    if source_attempt.get("lease", {}).get("state") == "quarantined":
        fail("repair lease expansion cannot use quarantined prior provenance")
    if packet_base != source_attempt.get("candidate_sha"):
        fail("repair lease expansion base SHA is stale or does not match the prior candidate")
    if not finding_matches_candidate(state, finding_ref, ticket["id"], packet_base):
        fail("repair lease expansion finding is not bound to the prior candidate")

    expanded: list[dict[str, Any]] = []
    lineage: list[dict[str, Any]] = []
    for violation in disallowed:
        path, operation = violation["path"], violation["operation"]
        if operation != "modify" or not zone_allows(ticket_zone, path, "create"):
            fail(f"repair packet write allowlist lacks prior-create provenance: {path} ({operation})")
        if any(path == item or path.startswith(item + "/") for item in denied):
            fail(f"repair lease expansion conflicts with packet deny list: {path}")
        attempts = validated_repair_path_lineage(
            p, state, ticket, source_attempt, path, packet_base
        )
        expanded.append({"path": path, "operations": ["modify"]})
        lineage.append({"path": path, "attempts": attempts})

    provenance = {
        "authorization_ref": authorization["id"],
        "finding_ref": finding_ref,
        "source_attempt_ref": source_attempt_ref,
        "candidate_sha": source_attempt["candidate_sha"],
        "packet_base_sha": packet_base,
        "expanded_entries": expanded,
        "lineage": lineage,
    }
    return requested, provenance


def review_criterion_id(record: dict[str, Any]) -> str:
    value = record.get("criterion_id", record.get("id"))
    return safe_id(value, "review criterion")


def validate_review_return_semantics(payload: dict[str, Any], packet: dict[str, Any]) -> None:
    packet_criteria = packet.get("criteria", [])
    required = [review_criterion_id(item) for item in packet_criteria]
    if len(required) != len(set(required)):
        fail("review packet has duplicate criteria")
    coverage = payload.get("coverage", [])
    coverage_ids = [review_criterion_id(item) for item in coverage]
    if len(coverage_ids) != len(set(coverage_ids)) or set(coverage_ids) != set(required):
        fail("review coverage must contain every packet criterion exactly once")
    if not payload.get("checks"):
        fail("review return requires non-empty independent checks")
    check_ids = ids_from_records(payload["checks"], "check_id", "review check")
    if any(not nonempty_string(item.get("evidence_ref"), "review check evidence_ref") for item in payload["checks"]):
        fail("review checks require evidence references")
    axes = packet.get("axes", [])
    if axes:
        if any(not item.get("axis") for item in payload["checks"]):
            fail("state-bound review checks require an explicit axis")
        checked_axes = {item["axis"] for item in payload["checks"]}
        if checked_axes != set(axes):
            fail(f"review return axes do not exactly match the packet: expected {sorted(set(axes))}, got {sorted(checked_axes)}")
    if not payload.get("context_refs"):
        fail("review return requires non-empty context evidence")
    if any(item.get("outcome") != "fulfilled" for item in coverage if payload.get("verdict") == "PASS"):
        fail("review PASS contains a non-fulfilled criterion")
    if payload.get("verdict") == "PASS" and any(item.get("outcome") != "fulfilled" for item in payload.get("checks", [])):
        fail("review PASS contains a failed, not-run, or unverifiable required check")
    for finding in payload.get("findings", []):
        if finding.get("impact") == "blocking" and payload.get("verdict") == "PASS":
            fail("review PASS contains a blocking finding")
    if not check_ids:
        fail("review return has no usable checks")
    resolution_entries = payload.get("finding_resolution", [])
    if resolution_entries and payload.get("verdict") != "PASS":
        fail("finding resolution claims require a PASS review")
    review_evidence = {
        *payload.get("context_refs", []),
        *(item.get("evidence_ref") for item in payload.get("checks", []) if item.get("evidence_ref")),
        *(ref for item in payload.get("coverage", []) for ref in item.get("evidence_refs", [])),
    }
    seen_resolution_pairs: set[tuple[str, str]] = set()
    for entry in resolution_entries:
        finding_ref = safe_id(entry.get("finding_ref"), "finding resolution finding_ref")
        candidate_ref = safe_id(entry.get("candidate_ref"), "finding resolution candidate_ref")
        pair = (finding_ref, candidate_ref)
        if pair in seen_resolution_pairs:
            fail("review return repeats a finding/candidate resolution claim")
        seen_resolution_pairs.add(pair)
        evidence_refs = entry.get("evidence_refs", [])
        if not evidence_refs or not set(evidence_refs).issubset(review_evidence):
            fail(f"finding resolution evidence must resolve to this review's own evidence: {finding_ref}")


def normalize_review_purpose(value: Any, *, packet_kind: str | None = None) -> str:
    """Normalize the Phase E review purpose without conflating it with transport."""
    if value == "ticket_change":
        value = "ticket_review"
    if value is None:
        return "final_g5" if packet_kind == "acceptance" else "ticket_review"
    if value not in ("ticket_review", "critical_axis", "final_g5"):
        fail("review purpose must be ticket_review, critical_axis, or final_g5")
    return value


def required_review_purposes(ticket: dict[str, Any] | None, purpose: str) -> list[str]:
    if purpose == "final_g5":
        return ["final_g5"]
    required = ["ticket_review"]
    if ticket and ticket.get("risk") == "critical":
        required.append("critical_axis")
    return required


def validate_review_integrity(
    receipt: dict[str, Any], current_raw: bytes, subject_fingerprint: str, *, require_stop: bool = True,
) -> None:
    if receipt.get("status") != "PASS":
        fail("review integrity receipt is not PASS")
    if receipt.get("candidate_fingerprint") != subject_fingerprint:
        fail("review integrity receipt is not bound to the exact candidate")
    if receipt.get("ledger_hash") != sha256_bytes(current_raw):
        fail("review integrity receipt is not bound to the current ledger publication")
    if require_stop and receipt.get("reviewer_stopped") is not True:
        fail("review integrity receipt lacks explicit reviewer stop evidence")


def append_review_qualification(
    state: dict[str, Any], subject_ref: str, subject_fingerprint: str,
    *, purpose: str, created_revision: int,
) -> dict[str, Any]:
    """Append an immutable aggregate over all accepted reviews for one exact subject."""
    ticket = next((item for item in state.get("tickets", []) if item.get("id") == subject_ref), None)
    required = required_review_purposes(ticket, purpose)
    accepted = [
        item for item in state.get("reviews", [])
        if item.get("accepted") is True
        and item.get("subject_fingerprint") == subject_fingerprint
        and item.get("purpose") in required
        and item.get("return_ref")
        and item.get("integrity_ref")
        and not item.get("invalidated_by")
    ]
    accepted.sort(key=lambda item: item.get("id", ""))
    satisfied = sorted({item["purpose"] for item in accepted if item.get("verdict") == "PASS"})
    blocking = any(item.get("verdict") in ("BLOCK", "UNVERIFIABLE") for item in accepted)
    result = "BLOCK" if blocking else ("PASS" if set(required).issubset(satisfied) else "INCOMPLETE")
    core = {
        "subject_ref": subject_ref,
        "subject_fingerprint": subject_fingerprint,
        "required_purposes": required,
        "accepted_review_refs": [item["id"] for item in accepted],
        "accepted_return_refs": [item["return_ref"] for item in accepted],
        "satisfied_purposes": satisfied,
        "result": result,
        "integrity_refs": [item["integrity_ref"] for item in accepted],
        "intent_revision": state.get("intent", {}).get("current_revision"),
    }
    qualification_id = f"QUAL-{sha256_bytes(canonical_bytes(core))[:16]}"
    prior = next((item for item in state.get("review_qualifications", []) if item.get("id") == qualification_id), None)
    if prior is not None:
        return prior
    qualification = {"id": qualification_id, **core, "created_revision": created_revision}
    state.setdefault("review_qualifications", []).append(qualification)
    return qualification


def qualification_by_id(state: dict[str, Any], qualification_id: str) -> dict[str, Any]:
    qualification = next(
        (item for item in state.get("review_qualifications", []) if item.get("id") == qualification_id), None
    )
    if qualification is None:
        fail("unknown review qualification")
    return qualification


def ledger_record_ids(state: dict[str, Any]) -> set[str]:
    result = {
        item["id"]
        for value in state.values()
        if isinstance(value, list)
        for item in value
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    if isinstance(state.get("design_publication"), dict):
        result.add(state["design_publication"]["id"])
    return result


def validate_return_against_attempt(p: dict[str, Path], state: dict[str, Any], attempt: dict[str, Any], payload: dict[str, Any], kind: str) -> dict[str, Any]:
    """State-bound validation shared by reviewer preflight and ingest."""
    definition = {"worker": "worker_return", "review": "review_return", "acceptance": "acceptance_return"}.get(kind)
    if definition is None:
        fail(f"unsupported return kind: {kind}")
    if attempt.get("kind") != kind:
        fail("supplied return kind does not match the registered attempt kind")
    root = schema()
    validate(payload, root["$defs"][definition], root, "$.return")
    validate_standalone_contract(payload, definition)
    identity = packet_identity(payload)
    if identity.get("run_id") != state["run_id"] or identity.get("attempt_id") != attempt["id"]:
        fail("return identity does not match the registered run/attempt")
    if kind == "worker" and identity.get("ticket_id") != attempt.get("subject_ref"):
        fail("worker return ticket_id does not match the registered ticket subject")
    if identity.get("packet_hash") != attempt.get("packet_hash"):
        fail("return packet hash mismatch")
    if identity.get("epoch") != attempt.get("epoch") or attempt.get("epoch") != state["owner"]["epoch"]:
        fail("return epoch mismatch; stale payload has no current authority")
    packet = stored_payload(p, attempt.get("packet_ref"), f"{kind} packet")
    packet_id = packet_identity(packet)
    if kind == "worker":
        ticket = next((item for item in state.get("tickets", []) if item.get("id") == attempt.get("subject_ref")), None)
        if ticket is None:
            fail("registered worker attempt references a missing ticket")
        validate_execution_binding(
            p, state, ticket, packet, kind=kind, attempt_id=attempt["id"],
            packet_hash=attempt.get("packet_hash"), route_id=attempt.get("route_ref"),
            attempt=attempt, return_identity=identity,
        )
        validate_worker_return_semantics(payload, packet)
    elif kind == "review":
        validate_review_return_semantics(payload, packet)

    packet_source = attempt.get("packet_source_revision", packet_id.get("source_revision"))
    packet_registration = attempt.get("packet_registration_revision", packet_id.get("registration_revision", packet_id.get("source_revision")))
    subject_revision = attempt.get("subject_revision", attempt.get("target_revision"))
    if packet_id.get("source_revision") is not None and identity.get("source_revision") != packet_source:
        fail("return source_revision does not match the immutable packet source revision")
    if packet_id.get("registration_revision") is not None and identity.get("registration_revision") != packet_registration:
        fail("return registration_revision does not match packet registration")
    if packet_id.get("subject_revision") is not None and identity.get("subject_revision") != subject_revision:
        fail("return subject_revision does not match the reviewed subject")
    if packet_id.get("intent_revision") is not None and identity.get("intent_revision") != attempt.get("intent_revision"):
        fail("return intent revision is stale")
    if packet_id.get("intent_document_ref") is not None and identity.get("intent_document_ref") != attempt.get("intent_document_ref"):
        fail("return intent document ref is stale")
    if packet_id.get("intent_document_hash") is not None and identity.get("intent_document_hash") != attempt.get("intent_document_hash"):
        fail("return intent document hash is stale")

    if kind == "review":
        if payload.get("subject_fingerprint") != attempt.get("subject_fingerprint", attempt.get("candidate_sha")):
            fail("review return subject fingerprint does not match the registered attempt")
        allowed_local = {review_criterion_id(item) for item in packet.get("criteria", [])}
        allowed_local.update(item.get("check_id") for item in payload.get("checks", []))
        allowed_local.update(packet.get("axes", []))
        known = ledger_record_ids(state)
        for finding in payload.get("findings", []):
            unknown = set(finding.get("affected_refs", [])) - known - allowed_local
            if unknown:
                fail(f"review finding contains refs outside ledger/packet scope: {sorted(unknown)}")
    return packet


def cmd_validate_return(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    state, _ = load_state(p)
    attempt = attempt_by_id(state, args.attempt_id)
    payload_path = Path(args.return_file).expanduser().resolve()
    payload = read_json(payload_path, "return")
    validate_return_against_attempt(p, state, attempt, payload, args.kind)
    return {
        "valid": True,
        "level": "state-bound",
        "kind": args.kind,
        "attempt_id": args.attempt_id,
        "packet_hash": attempt.get("packet_hash"),
        "subject_revision": attempt.get("subject_revision", attempt.get("target_revision")),
        "current_revision": state["revision"],
        "sha256": sha256_file(payload_path),
    }


def validate_acceptance_return_semantics(payload: dict[str, Any], required_ids: list[str]) -> None:
    outcomes = payload.get("outcomes", [])
    actual = [safe_id(item.get("criterion_id"), "acceptance criterion") for item in outcomes]
    if len(actual) != len(set(actual)) or set(actual) != set(required_ids):
        fail("acceptance outcomes must correspond exactly to active criteria")
    if not payload.get("checks"):
        fail("acceptance PASS requires non-empty independent checks")
    if any(not nonempty_string(item.get("evidence_ref"), "acceptance check evidence_ref") for item in payload.get("checks", [])):
        fail("acceptance checks require evidence references")
    if payload.get("verdict") == "PASS":
        if any(item.get("outcome") != "fulfilled" for item in outcomes):
            fail("acceptance PASS contains a non-fulfilled criterion")
        if any(item.get("outcome") != "fulfilled" for item in payload.get("checks", [])):
            fail("acceptance PASS contains a failed, not-run, or unverifiable required check")
        if any(item.get("impact") == "blocking" for item in payload.get("findings", [])):
            fail("acceptance PASS contains a blocking finding")


def validate_standalone_contract(value: dict[str, Any], kind: str) -> None:
    if kind == "worker_return":
        identity = packet_identity(value)
        if not HASH_RE.fullmatch(identity.get("packet_hash", "")) or not isinstance(identity.get("epoch"), int) or isinstance(identity.get("epoch"), bool):
            fail("worker_return identity requires packet_hash and owner epoch")
        checks = value.get("checks", [])
        criteria = value.get("criteria", [])
        ids_from_records(checks, "check_id", "worker check")
        ids_from_records(criteria, "criterion_id", "worker criterion")
        if value.get("status") == "DONE" and any(item.get("outcome") != "pass" for item in checks):
            fail("DONE worker return requires all checks to pass")
    elif kind == "review_return":
        identity = packet_identity(value)
        if not HASH_RE.fullmatch(identity.get("packet_hash", "")) or not isinstance(identity.get("epoch"), int) or isinstance(identity.get("epoch"), bool):
            fail("review_return identity requires packet_hash and owner epoch")
        coverage_ids = [review_criterion_id(item) for item in value.get("coverage", [])]
        if len(coverage_ids) != len(set(coverage_ids)):
            fail("review coverage contains duplicate criteria")
        if value.get("verdict") == "PASS" and any(item.get("outcome") != "fulfilled" for item in value.get("coverage", [])):
            fail("review PASS requires fulfilled coverage")
    elif kind == "acceptance_return":
        identity = packet_identity(value)
        if not HASH_RE.fullmatch(identity.get("packet_hash", "")) or not isinstance(identity.get("epoch"), int) or isinstance(identity.get("epoch"), bool):
            fail("acceptance_return identity requires packet_hash and owner epoch")
        outcome_ids = [safe_id(item.get("criterion_id"), "acceptance criterion") for item in value.get("outcomes", [])]
        if len(outcome_ids) != len(set(outcome_ids)):
            fail("acceptance outcomes contain duplicate criteria")
        if value.get("verdict") == "PASS" and any(item.get("outcome") != "fulfilled" for item in value.get("outcomes", [])):
            fail("acceptance PASS requires fulfilled outcomes")
    elif kind == "design_bundle":
        validate_design_bundle(value)


def ingest_payload(p: dict[str, Path], state: dict[str, Any], attempt_id: str, payload_path: Path, expected_packet_hash: str | None = None, kind: str | None = None) -> tuple[dict[str, Any], str, bytes]:
    payload_path = inbox_file(p, attempt_id, payload_path)
    raw = payload_path.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        fail(f"invalid return {payload_path}: {exc}")
    identity = packet_identity(payload)
    if identity.get("attempt_id") != attempt_id:
        fail("return attempt_id does not match exact inbox attempt")
    if expected_packet_hash and identity.get("packet_hash") != expected_packet_hash:
        fail("return packet hash mismatch")
    if identity.get("run_id") not in (None, state["run_id"]):
        fail("return run_id mismatch")
    if kind:
        definition = {"worker": "worker_return", "review": "review_return", "acceptance": "acceptance_return"}.get(kind)
        if definition:
            root = schema()
            validate(payload, root["$defs"][definition], root, "$.return")
            if kind == "worker":
                attempt = attempt_by_id(state, attempt_id)
                packet = stored_payload(p, attempt.get("packet_ref"), "worker packet")
                validate_worker_return_semantics(payload, packet)
            elif kind == "review":
                attempt = attempt_by_id(state, attempt_id)
                packet = stored_payload(p, attempt.get("packet_ref"), "review packet")
                validate_review_return_semantics(payload, packet)
    digest = sha256_bytes(raw)
    return payload, digest, raw


def append_issue(state: dict[str, Any], issue: dict[str, Any], *, source_ref: str | None = None, finding_ref: str | None = None) -> str:
    issue_id = issue.get("id") if isinstance(issue.get("id"), str) and issue.get("id") else f"issue-{sha256_bytes(canonical_bytes(issue))[:16]}"
    safe_id(issue_id, "issue_id")
    if issue_id in {item.get("id") for item in state.get("issues", [])}:
        issue_id = f"{issue_id}-{len(state.get('issues', [])) + 1}"
    cause = issue.get("cause", "unknown")
    if cause not in CAUSES:
        cause = "unknown"
    record = {"id": issue_id, "type": issue.get("type", "ingested_issue"), "cause": cause, "impact": issue.get("impact", "blocking"), "affected_refs": issue.get("affected_refs", []), "expected": issue.get("expected"), "actual": issue.get("actual"), "disposition": issue.get("disposition", "requires disposition"), "resolution_condition": issue.get("resolution_condition"), "owner": issue.get("owner"), "failure_signature": issue.get("failure_signature"), "finding_ref": finding_ref, "source_ref": source_ref, "intent_revision": state.get("intent", {}).get("current_revision"), "invalidated_by": []}
    state.setdefault("issues", []).append(record)
    return issue_id


def append_review_findings(state: dict[str, Any], payload: dict[str, Any], source_ref: str, digest: str, *, packet: dict[str, Any] | None = None, subject_ref: str | None = None) -> list[str]:
    refs: list[str] = []
    known = ledger_record_ids(state)
    packet_local: set[str] = set()
    if packet:
        packet_local.update(review_criterion_id(item) for item in packet.get("criteria", []))
        packet_local.update(packet.get("axes", []))
        packet_local.update(item.get("check_id") for item in payload.get("checks", []))
    for index, finding in enumerate(payload.get("findings", [])):
        finding_id = f"finding-{digest[:12]}-{index + 1}"
        reported_refs = finding.get("affected_refs", [])
        canonical_refs = [ref for ref in reported_refs if ref in known]
        if any(ref in packet_local and ref not in known for ref in reported_refs) and subject_ref:
            canonical_refs.append(subject_ref)
        canonical_refs = sorted(set(canonical_refs or ([subject_ref] if subject_ref else [])))
        record = {"id": finding_id, "axis": finding.get("axis", "unknown"), "impact": finding.get("impact", "advisory"), "claim": finding.get("claim", "ingested finding"), "expected": finding.get("expected", ""), "actual": finding.get("actual", ""), "evidence": finding.get("evidence", "return evidence"), "affected_refs": canonical_refs, "reported_affected_refs": reported_refs, "source_ref": source_ref, "intent_revision": state.get("intent", {}).get("current_revision"), "repair_contract_ref": None, "invalidated_by": []}
        if finding_id in {item.get("id") for item in state.get("findings", [])}:
            refs.append(finding_id)
            continue
        state.setdefault("findings", []).append(record)
        refs.append(finding_id)
        if record["impact"] == "blocking":
            append_issue(state, {"type": "review_finding", "cause": "unknown", "impact": "blocking", "affected_refs": record["affected_refs"], "expected": record["expected"], "actual": record["actual"], "disposition": "requires repair or adjudication", "resolution_condition": "finding independently resolved"}, source_ref=source_ref, finding_ref=finding_id)
    return refs


def base_state(control_root: Path, run_id: str, repo_root: Path, token: str) -> dict[str, Any]:
    state = {
        "schema_version": SCHEMA_VERSION, "run_id": run_id, "revision": 0, "previous_publication_hash": None,
        "updated_at": now(), "skill_version": SKILL_VERSION, "policy_version": POLICY_VERSION,
        "candidate_model_version": "1.1", "candidates": [],
        "review_model_version": "1.1", "review_qualifications": [], "repair_waves": [], "acceptance": [],
        "runtime_provenance": {"creation_skill_version": SKILL_VERSION, "current_schema_version": SCHEMA_VERSION, "last_mutating_skill_version": SKILL_VERSION, "compatibility_floor": COMPATIBILITY_FLOOR, "state_contract_version": STATE_CONTRACT_VERSION, "minimum_writer_version": WRITER_VERSION, "applied_migrations": []},
        "repository": {"control_root": str(control_root), "execution_root": str(repo_root), "common_dir": "", "initial_head": None, "branch": "", "checkout": str(repo_root), "inventory_ref": None, "instruction_refs": []},
        "owner": {"token": token, "epoch": 0, "observed_session": None, "handoff_ref": None, "attestation_ref": None},
        "run_settings": dict(DEFAULT_RUN_SETTINGS),
        "usage": default_usage(),
        "lifecycle": {"phase": "PREFLIGHT", "control": "ACTIVE", "reason": None, "issue_refs": [], "stop_target": None, "next_action": {"kind": "preflight", "subject_refs": [], "preconditions": [], "read_refs": ["phases/start.md"]}, "allowed_events": []},
    }
    refresh_control_projection(state)
    return state


def cmd_init(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    if not Path(args.repo_root).exists():
        fail("execution root does not exist")
    with Lock(p["lock"]):
        if p["ledger"].exists():
            fail("run already exists; use status/resume/recover instead of overwrite")
        runs_root = p["base"] / "runs"
        if runs_root.exists():
            for other in sorted(runs_root.iterdir()):
                other_ledger = other / "ledger.json"
                if not other_ledger.exists() or other.name == args.run_id:
                    continue
                other_state = read_json(other_ledger, "existing run ledger")
                validate_ledger(other_state)
                if other_state["lifecycle"]["control"] not in ("ACCEPTED", "FAILED", "CANCELLED"):
                    fail(f"another nonterminal run owns this repository: {other.name}")
        p["run"].mkdir(parents=True, exist_ok=False)
        state = base_state(p["root"], args.run_id, safe_root(args.repo_root, "execution root"), args.owner_token)
        state["run_settings"] = run_settings_from_args(args.request, args.interaction_mode, args.depth)
        validate_ledger(state)
        atomic_write(p["ledger"], canonical_bytes(state))
        result = copy.deepcopy(state)
        result["display"] = run_settings_display(state["run_settings"])
        return result


def cmd_status(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    state, raw = load_state(p)
    control_projection = derive_control_projection(state)
    findings_projection = finding_obligation_projection(state)
    if args.brief:
        lifecycle = state["lifecycle"]
        usage = copy.deepcopy(state.get("usage", default_usage()))
        binding = {"revision": state.get("intent", {}).get("current_revision"), "document_ref": state.get("intent", {}).get("document_ref"), "document_hash": state.get("intent", {}).get("document_hash")}
        settings = resolved_run_settings(state)
        brief = {"run_id": state["run_id"], "revision": state["revision"], "phase": lifecycle["phase"], "control": lifecycle["control"], "reason": lifecycle.get("reason"), "next_action": control_projection["next_action"], "allowed_events": control_projection["allowed_events"], "run_settings": settings, "preset_display": run_settings_display(settings), "issues": [i["id"] for i in state.get("issues", []) if i.get("impact") == "blocking" and not i.get("invalidated_by")], "findings": [f["id"] for f in state.get("findings", [])], "finding_status": [{"id": f["id"], "impact": f.get("impact"), "status": next((item["status"] for item in findings_projection["items"] if item["finding_ref"] == f["id"]), "unbound"), "current": next((item["current_applicability"] for item in findings_projection["items"] if item["finding_ref"] == f["id"]), False)} for f in state.get("findings", [])], "finding_projection": findings_projection, "candidates": state.get("candidates", []), "runtime_attempts": [{"id": a.get("id"), "liveness": runtime_liveness(a), "runtime_instance_id": (a.get("runtime") or {}).get("runtime_instance_id"), "reservation": a.get("lease", {}).get("state"), "protocol_recorded": isinstance(a.get("runtime"), dict)} for a in state.get("attempts", [])], "reviews": [{"id": r.get("id"), "subject": r.get("subject_fingerprint"), "verdict": r.get("verdict"), "review_kind": r.get("review_kind"), "reviewer_identity": r.get("reviewer_identity"), "reviewer_role": r.get("reviewer_role"), "current": not bool(r.get("invalidated_by")), "finding_refs": r.get("finding_refs", [])} for r in state.get("reviews", [])], "design_publication": state.get("design_publication"), "design_publication_history": state.get("design_publication_history", []), "requirements_publications": state.get("requirements_publications", []), "design_review_attempts": [{"id": a.get("id"), "kind": a.get("mode"), "state": a.get("state"), "result": a.get("review_result"), "reviewer_identity": a.get("reviewer_identity"), "reviewer_role": a.get("reviewer_role")} for a in state.get("attempts", []) if a.get("mode") in ("coverage", "plan")], "adjudications": [d.get("id") for d in state.get("decisions", []) if d.get("type") == "reviewer_adjudication"], "intent": binding, "version_provenance": state.get("runtime_provenance", {"creation_skill_version": state.get("skill_version"), "current_schema_version": state.get("schema_version"), "last_mutating_skill_version": state.get("skill_version"), "compatibility_floor": COMPATIBILITY_FLOOR, "applied_migrations": []}), "consumer_invalidation_count": len(state.get("invalidations", [])), "usage": usage, "evidence_count": len(state.get("evidence", [])), "ledger_bytes": len(raw), "ledger_hash": sha256_bytes(raw)}
        brief["usage"]["counters"]["brief_bytes"] = len(canonical_bytes(brief))
        return brief
    settings = resolved_run_settings(state)
    current_blockers = [
        item["id"] for item in state.get("issues", [])
        if item.get("impact") == "blocking" and not item.get("invalidated_by")
    ]
    status_counts = {kind: sum(1 for item in findings_projection["items"] if item["status"] == kind) for kind in ("current", "historical", "unbound", "resolved", "superseded")}
    legacy_current_findings = sum(1 for item in state.get("findings", []) if not item.get("invalidated_by"))
    return {
        "run_id": state["run_id"], "revision": state["revision"],
        "phase": state["lifecycle"]["phase"], "control": state["lifecycle"]["control"],
        "next_action": control_projection["next_action"], "allowed_events": control_projection["allowed_events"],
        "run_settings": settings, "preset_display": run_settings_display(settings),
        "ticket_counts": {s: sum(1 for t in state.get("tickets", []) if t.get("state") == s) for s in ("PLANNED", "READY", "RUNNING", "CANDIDATE", "REVIEW", "INTEGRATED", "BLOCKED", "STALE")},
        "attempts": len(state.get("attempts", [])), "runtime_attempts": [{"id": a.get("id"), "liveness": runtime_liveness(a), "runtime_instance_id": (a.get("runtime") or {}).get("runtime_instance_id"), "reservation": a.get("lease", {}).get("state"), "protocol_recorded": isinstance(a.get("runtime"), dict)} for a in state.get("attempts", [])], "blockers": current_blockers,
        "finding_counts": {"current": legacy_current_findings, "historical": len(state.get("findings", [])) - legacy_current_findings, "total": len(state.get("findings", []))},
        "finding_status_counts": status_counts,
        "finding_projection": findings_projection, "candidates": state.get("candidates", []),
        "ledger_hash": sha256_bytes(raw),
    }


def cmd_publish_usage(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    event_path = Path(args.event_file).expanduser().resolve()
    event = read_json(event_path, "usage event")
    root = schema()
    validate(event, root["$defs"]["usage_event"], root, "$.usage_event")
    raw = event_path.read_bytes()
    event_hash = sha256_bytes(raw)
    event_ref = f"objects/{event_hash}"
    with Lock(p["lock"]):
        state, previous_raw = load_mutation_state(p, args.owner_token, args.revision)
        admit_event(state, "usage.publish")
        usage = state.setdefault("usage", default_usage())
        usage.setdefault("counters", zero_usage()); usage.setdefault("trace", []); usage.setdefault("shared_setup", zero_usage()); usage.setdefault("gate_costs", {f"G{i}": zero_usage() for i in range(7)})
        if event["id"] in {item.get("id") for item in usage["trace"]}:
            fail("usage event ID already published")
        delta = event["delta"]
        add_usage(usage["counters"], delta)
        scope = event.get("scope", "run")
        if scope == "shared_setup":
            add_usage(usage["shared_setup"], delta)
        elif scope.startswith("G"):
            add_usage(usage["gate_costs"].setdefault(scope, zero_usage()), delta)
        token_reason = event.get("token_reason")
        if event.get("tokens") is None:
            usage["tokens"] = None
            usage["token_reason"] = token_reason or "token_meter_unavailable"
            usage["unknown_reason"] = usage["token_reason"]
        else:
            usage["tokens"] = event["tokens"]
            usage["token_reason"] = token_reason
            usage["unknown_reason"] = None
        usage["trace"].append({"id": event["id"], "kind": event["kind"], "actor": event["actor"], "subject_ref": event.get("subject_ref"), "delta": delta, "evidence_ref": event_ref, "recorded_at": now()})
        for item in event.get("evidence", []):
            evidence_id = item["id"]
            if evidence_id in {record.get("id") for record in state.get("evidence", [])}:
                continue
            state.setdefault("evidence", []).append({"id": evidence_id, "hash": item["hash"], "source": "usage_publication", "scenario": item.get("scenario"), "outcome": item["outcome"], "observer": item["observer"], "subject": event.get("subject_ref")})
        state["revision"] += 1
        state["previous_publication_hash"] = sha256_bytes(previous_raw)
        state["updated_at"] = now()
        validate_ledger(state, verify_files=False)
        object_store(p, raw)
        publish(p, state, previous_raw, "usage")
    return {"published": True, "event_id": event["id"], "event_ref": event_ref, "scope": event.get("scope", "run"), "tokens": state["usage"].get("tokens"), "token_reason": state["usage"].get("token_reason"), "revision": state["revision"]}


def cmd_render_view(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    state, raw = load_state(p)
    source_hash = sha256_bytes(raw)
    lifecycle = state["lifecycle"]
    blocking = [item["id"] for item in state.get("issues", []) if item.get("impact") == "blocking" and not item.get("invalidated_by")]
    settings = resolved_run_settings(state)
    lines = [f"# Autopilot {args.kind}", "", f"- Run: `{state['run_id']}`", f"- Source revision: `{state['revision']}`", f"- Source ledger SHA-256: `{source_hash}`", f"- Phase/control: `{lifecycle['phase']} × {lifecycle['control']}`", f"- {run_settings_display(settings)}", f"- Next action: `{lifecycle['next_action']['kind']}`"]
    if blocking:
        lines.extend(["", "## Blocking issues", "", *[f"- `{item}`" for item in blocking]])
    if args.kind == "final-report":
        acceptances = state.get("acceptance", [])
        latest = acceptances[-1] if acceptances else None
        lines.extend(["", "## Candidate and acceptance", "", f"- Candidate: `{(latest or {}).get('candidate_fingerprint', 'unknown')}`", f"- Intent revision: `{(latest or {}).get('intent_revision', 'unknown')}`", f"- Acceptance transport: `{(latest or {}).get('transport', 'not_recorded')}`", f"- Context grade: `{(latest or {}).get('context_grade', 'not_recorded')}`", "- Exclusions and unverifiable criteria remain blocking unless explicitly amended."])
    output = p["run"] / "views" / f"{args.kind}.md"
    atomic_write(output, ("<!-- generated: ledger.py; not authoritative state -->\n\n" + "\n".join(lines) + "\n").encode("utf-8"))
    return {"generated": str(output), "source_revision": state["revision"], "source_hash": source_hash}


def cmd_validate(args: argparse.Namespace) -> dict[str, Any]:
    target = Path(args.file).expanduser().resolve()
    value = read_json(target, "contract")
    root = schema()
    if args.kind == "ledger":
        validate_ledger(value)
    else:
        defs = root.get("$defs", {})
        if args.kind not in defs:
            fail(f"unknown schema definition: {args.kind}")
        validate(value, defs[args.kind], root, "$")
        validate_standalone_contract(value, args.kind)
    return {"valid": True, "kind": args.kind, "sha256": sha256_file(target)}


def cmd_diagnose(args: argparse.Namespace) -> dict[str, Any]:
    """Read-only shape and semantic-writer diagnostic; never upgrades state."""
    p = paths(args.control_root, args.run_id)
    regular_non_symlink(p["ledger"])
    raw = p["ledger"].read_bytes()
    try:
        state = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        return {"read_only": True, "supported": False, "shape_supported": False, "readable": False, "valid": False, "mutation_eligible": False, "reason": f"corrupt ledger: {exc}", "required_action": "recover from a verified previous publication or snapshot", "ledger_hash": sha256_bytes(raw)}
    schema_version = state.get("schema_version")
    supported = schema_version == SCHEMA_VERSION
    result = {
        "read_only": True,
        "supported": supported,
        "shape_supported": supported,
        "readable": False,
        "valid": False,
        "mutation_eligible": False,
        "schema_version": schema_version,
        "supported_schema_version": SCHEMA_VERSION,
        "state_contract_version": (state.get("runtime_provenance") or {}).get("state_contract_version") if isinstance(state.get("runtime_provenance"), dict) else None,
        "minimum_writer_version": (state.get("runtime_provenance") or {}).get("minimum_writer_version") if isinstance(state.get("runtime_provenance"), dict) else None,
        "current_writer_version": WRITER_VERSION,
        "run_id": state.get("run_id"),
        "revision": state.get("revision"),
        "creation_skill_version": state.get("skill_version"),
        "runtime_provenance": state.get("runtime_provenance"),
        "ledger_hash": sha256_bytes(raw),
    }
    if not supported:
        result["reason"] = "unknown shape schema; use a helper that supports it; mutation is forbidden"
        result["required_action"] = "upgrade to a helper that supports this shape schema"
        return result
    try:
        validate_ledger(state)
        result["valid"] = True
        result["readable"] = True
    except LedgerError as exc:
        result["valid"] = False
        result["reason"] = str(exc)
        result["required_action"] = "repair or migrate the invalid ledger before mutation"
        return result
    reason = mutation_ineligibility(state)
    if reason is None:
        result["mutation_eligible"] = True
    else:
        result["reason"] = reason
        result["required_action"] = reason
    return result


def _legacy_attempt_order(attempt: dict[str, Any], fallback: int) -> tuple[int, int, str]:
    """Return a deterministic durable ordering key without consulting object files."""
    for field in ("attempt_created_revision", "packet_registration_revision", "return_source_revision", "subject_revision"):
        value = attempt.get(field)
        if isinstance(value, int) and not isinstance(value, bool):
            return (value, fallback, str(attempt.get("id", "")))
    return (-1, fallback, str(attempt.get("id", "")))


def _legacy_structural_analysis(state: dict[str, Any]) -> dict[str, Any]:
    """Project legacy state for diagnosis using ledger-resident data only."""
    attempts = state.get("attempts", [])
    attempts_by_id = {item["id"]: item for item in attempts}
    tickets_by_id = {item["id"]: item for item in state.get("tickets", [])}
    contracts_by_id = {item["id"]: item for item in state.get("contracts", [])}
    evidence_ids = {item["id"] for item in state.get("evidence", [])}
    attempt_positions = {item["id"]: index for index, item in enumerate(attempts)}

    intersections: list[dict[str, str]] = []
    publication = state.get("design_publication")
    if isinstance(publication, dict) and publication.get("status") == "PUBLISHED":
        published_tickets = set(publication.get("ticket_refs", []))
        for contract_ref in sorted(set(publication.get("contract_refs", []))):
            contract = contracts_by_id.get(contract_ref)
            if contract is None:
                continue
            producer_refs = set(contract.get("producer_refs", []))
            for ticket_ref in sorted(published_tickets & producer_refs):
                ticket = tickets_by_id.get(ticket_ref)
                if ticket is not None and contract_ref in set(ticket.get("contract_refs", [])):
                    intersections.append({"contract_ref": contract_ref, "ticket_ref": ticket_ref})

    candidates: list[dict[str, Any]] = []
    for ticket_id, ticket in sorted(tickets_by_id.items()):
        current_attempt_ref = ticket.get("current_attempt")
        attempt = attempts_by_id.get(current_attempt_ref)
        if (
            attempt is None
            or attempt.get("kind") != "worker"
            or attempt.get("subject_ref") != ticket_id
            or not attempt.get("continuation_ref")
            or not attempt.get("candidate_sha")
        ):
            continue
        candidates.append({
            "ticket_ref": ticket_id,
            "ticket_state": ticket.get("state"),
            "attempt_ref": attempt["id"],
            "attempt_state": attempt.get("state"),
            "candidate_sha": attempt["candidate_sha"],
            "continuation_ref": attempt["continuation_ref"],
            "qualification": "continuation_only",
            "integrated": False,
        })

    current_reviews: list[dict[str, Any]] = []
    current_review_ids: dict[str, str] = {}
    for candidate in candidates:
        matching = [
            (index, item)
            for index, item in enumerate(attempts)
            if item.get("kind") == "review"
            and item.get("subject_ref") == candidate["ticket_ref"]
            and item.get("candidate_sha") == candidate["candidate_sha"]
            and item.get("state") == "RETURNED"
            and isinstance(item.get("return_ref"), str)
            and bool(item.get("return_ref"))
        ]
        if not matching:
            current_reviews.append({
                "ticket_ref": candidate["ticket_ref"],
                "candidate_sha": candidate["candidate_sha"],
                "attempt_ref": None,
                "state": None,
                "review_result": None,
                "attempt_revision": None,
                "return_source_revision": None,
                "finding_refs": [],
                "finding_count": 0,
            })
            continue
        index, review = max(matching, key=lambda pair: _legacy_attempt_order(pair[1], pair[0]))
        finding_refs = sorted(set(review.get("finding_refs", [])))
        current_review_ids[candidate["ticket_ref"]] = review["id"]
        current_reviews.append({
            "ticket_ref": candidate["ticket_ref"],
            "candidate_sha": candidate["candidate_sha"],
            "attempt_ref": review["id"],
            "state": review.get("state"),
            "review_result": review.get("review_result"),
            "attempt_revision": review.get("attempt_created_revision"),
            "return_source_revision": review.get("return_source_revision"),
            "finding_refs": finding_refs,
            "finding_count": len(finding_refs),
        })

    historical_ticket_reviews: list[dict[str, Any]] = []
    historical_ticket_finding_refs: set[str] = set()
    for ticket_id in sorted(candidate["ticket_ref"] for candidate in candidates):
        current_review_id = current_review_ids.get(ticket_id)
        current_order = (
            _legacy_attempt_order(attempts_by_id[current_review_id], attempt_positions[current_review_id])
            if current_review_id is not None
            else None
        )
        for index, attempt in enumerate(attempts):
            if (
                attempt.get("kind") != "review"
                or attempt.get("subject_ref") != ticket_id
                or attempt.get("id") == current_review_id
                or (current_order is not None and _legacy_attempt_order(attempt, index) >= current_order)
            ):
                continue
            finding_refs = sorted(set(attempt.get("finding_refs", [])))
            if not finding_refs:
                continue
            historical_ticket_finding_refs.update(finding_refs)
            historical_ticket_reviews.append({
                "ticket_ref": ticket_id,
                "review_attempt_ref": attempt["id"],
                "state": attempt.get("state"),
                "finding_refs": finding_refs,
                "finding_count": len(finding_refs),
            })
    historical_ticket_reviews.sort(key=lambda item: (item["ticket_ref"], item["review_attempt_ref"]))

    historical_design_reviews: list[dict[str, Any]] = []
    historical_design_finding_refs: set[str] = set()
    for attempt in attempts:
        if attempt.get("kind") != "review" or attempt.get("mode") not in ("coverage", "plan"):
            continue
        finding_refs = sorted(set(attempt.get("finding_refs", [])))
        if finding_refs:
            historical_design_finding_refs.update(finding_refs)
            historical_design_reviews.append({
                "review_attempt_ref": attempt["id"],
                "review_kind": attempt.get("mode"),
                "state": attempt.get("state"),
                "finding_refs": finding_refs,
                "finding_count": len(finding_refs),
            })
    historical_design_reviews.sort(key=lambda item: item["review_attempt_ref"])

    external_blockers: list[dict[str, Any]] = []
    external_causes = {"environment", "permission", "user_intent"}
    for issue in state.get("issues", []):
        if issue.get("impact") != "blocking" or issue.get("invalidated_by"):
            continue
        issue_type = str(issue.get("type", "")).lower()
        type_tokens = set(re.split(r"[^a-z0-9]+", issue_type))
        source_ref = issue.get("source_ref")
        source_attempt = attempts_by_id.get(source_ref)
        source_evidence = source_ref in evidence_ids if isinstance(source_ref, str) else False
        if source_attempt is None and not source_evidence:
            continue
        basis: list[str] = ["source_ref resolves to a durable ledger attempt" if source_attempt else "source_ref resolves to durable ledger evidence"]
        if "external" in type_tokens:
            basis.append("issue type explicitly marks an external blocker")
        if issue.get("cause") in external_causes:
            basis.append(f"cause is {issue['cause']}")
        if len(basis) == 1:
            continue
        external_blockers.append({
            "issue_ref": issue["id"],
            "type": issue.get("type"),
            "cause": issue.get("cause"),
            "source_ref": source_ref,
            "source_attempt_state": source_attempt.get("state") if source_attempt else None,
            "affected_refs": sorted(set(issue.get("affected_refs", []))),
            "classification_basis": basis,
        })
    external_blockers.sort(key=lambda item: item["issue_ref"])

    next_action = state.get("lifecycle", {}).get("next_action", {})
    action_kind = next_action.get("kind") if isinstance(next_action, dict) else None
    subject_refs = next_action.get("subject_refs", []) if isinstance(next_action, dict) else []
    is_await = isinstance(action_kind, str) and action_kind.startswith("await_")
    referenced_attempts = [attempts_by_id[ref] for ref in subject_refs if ref in attempts_by_id]
    unresolved_subject_refs = sorted(ref for ref in subject_refs if ref not in attempts_by_id)
    terminal_states = {"RETURNED", "LOST", "INTERRUPTED"}
    stale = bool(
        is_await
        and referenced_attempts
        and not unresolved_subject_refs
        and all(attempt.get("state") in terminal_states for attempt in referenced_attempts)
    )
    stale_reasons = []
    if stale:
        for attempt in sorted(referenced_attempts, key=lambda item: item["id"]):
            stale_reasons.append({
                "attempt_ref": attempt["id"],
                "kind": attempt.get("kind"),
                "state": attempt.get("state"),
                "reason": f"await target is terminal: attempt state is {attempt.get('state')}",
            })

    return {
        "revision": state.get("revision"),
        "lifecycle": {
            "phase": state.get("lifecycle", {}).get("phase"),
            "control": state.get("lifecycle", {}).get("control"),
        },
        "accepted_design_intersections": {
            "records": intersections,
            "total_count": len(intersections),
            "distinct_ticket_count": len({item["ticket_ref"] for item in intersections}),
        },
        "current_candidates": candidates,
        "current_review_attempts": current_reviews,
        "historical_ticket_review_findings": {
            "reviews": historical_ticket_reviews,
            "finding_refs": sorted(historical_ticket_finding_refs),
            "finding_count": len(historical_ticket_finding_refs),
        },
        "historical_design_findings": {
            "reviews": historical_design_reviews,
            "finding_refs": sorted(historical_design_finding_refs),
            "finding_count": len(historical_design_finding_refs),
        },
        "active_external_blockers": external_blockers,
        "next_action_analysis": {
            "stored": next_action,
            "await_action": is_await,
            "stale": stale if is_await else None,
            "referenced_attempts": [
                {"attempt_ref": item["id"], "kind": item.get("kind"), "state": item.get("state")}
                for item in sorted(referenced_attempts, key=lambda item: item["id"])
            ],
            "unresolved_subject_refs": unresolved_subject_refs,
            "stale_reasons": stale_reasons,
        },
    }


def cmd_diagnose_legacy(args: argparse.Namespace) -> dict[str, Any]:
    """Read one standalone ledger file and report structural diagnostics only."""
    target = Path(args.file)
    result: dict[str, Any] = {
        "read_only": True,
        "source_path": str(target.absolute()),
        "source_sha256": None,
        "schema_version": None,
        "shape_supported": False,
        "valid": False,
        "validation_error": None,
        "mutation_eligible": False,
        "mutation_reason": "ledger has not passed known-schema validation",
        "revision": None,
        "lifecycle": {"phase": None, "control": None},
    }
    try:
        regular_non_symlink(target)
        raw = target.read_bytes()
    except (LedgerError, OSError) as exc:
        result["validation_error"] = str(exc)
        result["mutation_reason"] = "selected ledger could not be safely read; mutation is forbidden"
        return result

    result["source_sha256"] = sha256_bytes(raw)
    try:
        state = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        result["validation_error"] = f"corrupt ledger JSON: {exc}"
        result["mutation_reason"] = "corrupt ledger JSON; mutation is forbidden"
        return result

    if not isinstance(state, dict):
        result["validation_error"] = "ledger root must be an object"
        result["mutation_reason"] = "invalid ledger shape; mutation is forbidden"
        return result
    result["schema_version"] = state.get("schema_version")
    result["revision"] = state.get("revision")
    lifecycle = state.get("lifecycle")
    if isinstance(lifecycle, dict):
        result["lifecycle"] = {"phase": lifecycle.get("phase"), "control": lifecycle.get("control")}
    result["shape_supported"] = state.get("schema_version") == SCHEMA_VERSION
    if not result["shape_supported"]:
        result["validation_error"] = f"unsupported shape schema {state.get('schema_version')!r}; supported schema is {SCHEMA_VERSION}"
        result["mutation_reason"] = "unknown shape schema; mutation is forbidden"
        return result
    try:
        validate_ledger(state, verify_files=False)
    except (LedgerError, KeyError, TypeError, ValueError, IndexError) as exc:
        result["validation_error"] = str(exc)
        result["mutation_reason"] = "known-schema ledger validation failed; mutation is forbidden"
        return result

    result["valid"] = True
    reason = mutation_ineligibility(state)
    result["mutation_eligible"] = reason is None
    result["mutation_reason"] = reason
    result.update(_legacy_structural_analysis(state))
    return result


def cmd_ingest(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    integrity = read_json(Path(args.integrity_receipt), "review integrity receipt") if getattr(args, "integrity_receipt", None) else None
    integrity_raw = canonical_bytes(integrity) if integrity is not None else None
    qualification_ref: str | None = None
    with Lock(p["lock"]):
        state, previous_raw = load_mutation_state(p, args.owner_token)
        admit_event(state, "attempt.ingest")
        if state["lifecycle"]["control"] in ("ACCEPTED", "FAILED", "CANCELLED"):
            fail("terminal run is immutable; start a successor run")
        attempt = attempt_by_id(state, args.attempt_id)
        if args.kind != attempt.get("kind"):
            fail("supplied return kind does not match the registered attempt kind")
        return_path = inbox_file(p, args.attempt_id, Path(args.return_file))
        proposed_digest = sha256_file(return_path)
        if attempt.get("state") == "RETURNED":
            if attempt.get("return_ref") == f"objects/{proposed_digest}":
                payload = read_json(return_path, "return")
                validate_return_against_attempt(p, state, attempt, payload, args.kind)
                return {"ingested": True, "idempotent": True, "attempt_id": args.attempt_id, "return_ref": attempt["return_ref"], "status": attempt.get("review_result", "RETURNED"), "revision": state["revision"]}
            fail("conflicting duplicate return for a terminal attempt")
        if attempt.get("state") in ("LOST", "INTERRUPTED"):
            fail("return conflicts with a terminal lost/interrupted attempt")
        runtime = attempt.get("runtime")
        if isinstance(runtime, dict) and runtime_liveness(attempt) == "not_started":
            fail("return ingestion conflicts with an exact not_started runtime observation")
        if isinstance(runtime, dict) and runtime.get("return_observation_ref"):
            observed_return = stored_payload(p, runtime["return_observation_ref"], "runtime return observation")
            if observed_return.get("return_hash") != proposed_digest:
                fail("ingested return bytes do not match the exact runtime return_observed receipt")
        if state["revision"] != args.revision:
            fail(f"revision mismatch: expected {args.revision}, current {state['revision']}")
        payload, digest, return_raw = ingest_payload(p, state, args.attempt_id, Path(args.return_file), attempt.get("packet_hash"), args.kind)
        identity = packet_identity(payload)
        packet = validate_return_against_attempt(p, state, attempt, payload, args.kind)
        review_purpose = normalize_review_purpose(packet.get("purpose"), packet_kind="review") if args.kind == "review" else None
        phase_e_review = bool(args.kind == "review" and packet.get("purpose") is not None and attempt.get("mode") == "change")
        if phase_e_review:
            require_runtime_stopped(p, attempt, "Phase E review qualification")
            if attempt.get("review_purpose") not in (None, review_purpose):
                fail("review return purpose does not match the registered attempt")
            if integrity is None or integrity_raw is None:
                fail("Phase E review acceptance requires a hash-bound integrity receipt")
            validate_review_integrity(integrity, previous_raw, payload.get("subject_fingerprint", ""))
        if args.kind == "review" and attempt.get("mode") in ("coverage", "plan"):
            publication = current_design_publication(state)
            if attempt.get("subject_ref") != publication.get("id") or attempt.get("subject_fingerprint") != publication.get("publication_hash") or payload.get("subject_fingerprint") != publication.get("publication_hash"):
                fail("design review return is not bound to the current published bundle")
            if identity.get("intent_revision") not in (None, publication.get("intent_revision")):
                fail("design review return intent revision is stale")
        next_state = copy.deepcopy(state)
        target = attempt_by_id(next_state, args.attempt_id)
        target["state"] = "RETURNED"
        target["return_ref"] = f"objects/{digest}"
        target["return_source_revision"] = identity.get("source_revision", target.get("packet_source_revision"))
        if args.kind == "review":
            target["review_result"] = payload.get("verdict")
            # A return is not a stop observation. Runtime-protocol reservations
            # remain checked out until exact stop/reconciliation is recorded.
            if target.get("lease", {}).get("state") == "active" and (
                not isinstance(target.get("runtime"), dict) or runtime_stop_proven(p, target)
            ):
                target["lease"]["state"] = "released"
        target["finding_refs"] = append_review_findings(next_state, payload, args.attempt_id, digest, packet=packet if args.kind == "review" else None, subject_ref=target.get("subject_ref"))
        if args.kind == "worker":
            ticket_for_attempt = next((item for item in next_state.get("tickets", []) if item.get("id") == target.get("subject_ref")), None)
            if ticket_for_attempt and ticket_for_attempt.get("current_worker_attempt") == target.get("id"):
                ticket_for_attempt["current_worker_attempt"] = None
        write_set_violations = worker_return_write_set_violations(payload, attempt.get("lease", {})) if args.kind == "worker" else []
        if write_set_violations:
            issue_id = append_issue(next_state, {
                "id": f"write-set-{digest[:12]}",
                "type": "write_set_violation",
                "cause": "ownership",
                "impact": "blocking",
                "affected_refs": [target.get("subject_ref"), args.attempt_id],
                "expected": "worker return files remain within the active lease zone and allowed operations",
                "actual": json.dumps(write_set_violations, sort_keys=True),
                "disposition": "quarantine lease and reconcile actual checkout ownership before retry",
                "resolution_condition": "actual write set audited and a fresh scoped attempt is authorized",
            }, source_ref=args.attempt_id)
            target["finding_refs"].append(issue_id)
            target["lease"]["state"] = "quarantined"
        if payload.get("status") in ("BLOCKED", "FAILED", "HANDOFF") or write_set_violations:
            for issue in payload.get("issues", []):
                issue_id = append_issue(next_state, issue, source_ref=args.attempt_id)
                if issue_id not in target["finding_refs"]:
                    target["finding_refs"].append(issue_id)
            ticket = next((item for item in next_state.get("tickets", []) if item.get("id") == target.get("subject_ref")), None)
            if ticket and ticket.get("state") not in ("CANCELLED", "STALE"):
                ticket["state"] = "BLOCKED"
            next_state["lifecycle"]["control"] = "BLOCKED"
            next_state["lifecycle"]["reason"] = f"{args.kind}_{payload.get('status').lower()}"
            next_state["lifecycle"]["issue_refs"] = sorted(set(next_state["lifecycle"].get("issue_refs", []) + target["finding_refs"]))
            next_state["lifecycle"]["next_action"] = {"kind": "triage_or_repair", "subject_refs": [args.attempt_id], "preconditions": ["durable cause/finding contract", "no unchanged retry"], "read_refs": ["phases/execute.md", "references/routing.md"]}
        elif args.kind == "worker" and payload.get("status") == "DONE":
            next_state["lifecycle"]["next_action"] = {
                "kind": "audit_worker_return_and_prepare_candidate",
                "subject_refs": [args.attempt_id],
                "preconditions": ["worker stopped", "actual write set audited", "candidate effect prepared"],
                "read_refs": ["phases/execute.md", "references/safety.md"],
            }
        if args.kind == "review" and payload.get("verdict") == "PASS":
            ticket = next((item for item in next_state.get("tickets", []) if item.get("id") == target.get("subject_ref")), None)
            worker = current_candidate_producer(next_state, ticket) if ticket else None
            if ticket and worker and worker.get("continuation_ref"):
                next_state["lifecycle"]["control"] = "BLOCKED"
                next_state["lifecycle"]["reason"] = "blocked_continuation_candidate_reviewed"
                next_state["lifecycle"]["next_action"] = {
                    "kind": "resolve_blocker_or_authorize_candidate_bound_repair",
                    "subject_refs": [ticket["id"], worker["id"], *target.get("finding_refs", [])],
                    "preconditions": ["external/out-of-scope blocker remains durable", "review PASS does not mark the ticket DONE or INTEGRATED"],
                    "read_refs": ["phases/execute.md", "references/routing.md"],
                }
        if args.kind == "review" and target.get("subject_ref") in {item.get("id") for item in next_state.get("tickets", [])}:
            reviewed_ticket = next(item for item in next_state["tickets"] if item.get("id") == target.get("subject_ref"))
            candidate = current_candidate_record(next_state, reviewed_ticket)
            if candidate and target.get("candidate_sha") == candidate.get("sha"):
                candidate["review_status"] = payload.get("verdict") if payload.get("verdict") in ("PASS", "BLOCK") else "PENDING"
        if args.kind == "review":
            review_id = f"REV-{digest[:16]}"
            if review_id not in {item.get("id") for item in next_state.get("reviews", [])}:
                review = {"id": review_id, "attempt_ref": target.get("id"), "purpose": review_purpose if phase_e_review else None, "mandate": stored_payload(p, target.get("packet_ref"), "review packet").get("mandate", "review"), "subject_fingerprint": payload.get("subject_fingerprint", ""), "verdict": payload.get("verdict"), "accepted": phase_e_review, "return_ref": f"objects/{digest}", "integrity_ref": f"objects/{sha256_bytes(integrity_raw)}" if integrity_raw is not None and phase_e_review else None, "context_refs": payload.get("context_refs", []), "finding_refs": target["finding_refs"], "finding_resolution": copy.deepcopy(payload.get("finding_resolution", [])), "intent_revision": next_state.get("intent", {}).get("current_revision"), "reviewer_identity": target.get("reviewer_identity"), "reviewer_role": target.get("reviewer_role"), "review_kind": target.get("mode") if target.get("mode") in ("coverage", "plan") else None, "target_artifact_refs": target.get("target_artifact_refs", []), "target_artifact_versions": target.get("target_artifact_versions", []), "target_revision": target.get("target_revision"), "invalidated_by": []}
                next_state.setdefault("reviews", []).append(review)
            current_review = next(item for item in next_state.get("reviews", []) if item.get("id") == review_id)
            if phase_e_review:
                qualification = append_review_qualification(
                    next_state, target.get("subject_ref"), payload.get("subject_fingerprint", ""),
                    purpose=review_purpose, created_revision=state["revision"] + 1,
                )
                qualification_ref = qualification["id"]
                candidate = next(
                    (item for item in next_state.get("candidates", []) if item.get("ticket_ref") == target.get("subject_ref") and item.get("sha") == payload.get("subject_fingerprint")),
                    None,
                )
                if candidate is not None:
                    candidate["review_status"] = "PASS" if qualification["result"] == "PASS" else ("BLOCK" if qualification["result"] == "BLOCK" else "PENDING")
            prior = [
                item for item in next_state.get("reviews", [])
                if item.get("subject_fingerprint") == current_review.get("subject_fingerprint")
                and item.get("review_kind") == current_review.get("review_kind")
                and item.get("mandate") == current_review.get("mandate")
                and item.get("target_revision") == current_review.get("target_revision")
                and not item.get("invalidated_by")
            ]
            verdicts = {item.get("verdict") for item in prior}
            if len(verdicts) > 1:
                disagreement = append_issue(next_state, {"id": f"disagreement-{digest[:12]}", "type": "reviewer_disagreement", "cause": "oracle", "impact": "blocking", "affected_refs": [target.get("subject_ref"), *[item.get("id") for item in prior]], "expected": "reviewers agree or adjudication is recorded", "actual": json.dumps(sorted(str(item) for item in verdicts)), "disposition": "adjudication required", "resolution_condition": "durable adjudication decision"}, source_ref=review_id)
                next_state["lifecycle"]["control"] = "BLOCKED"
                next_state["lifecycle"]["reason"] = "reviewer_disagreement"
                next_state["lifecycle"]["issue_refs"] = sorted(set(next_state["lifecycle"].get("issue_refs", []) + [disagreement]))
                next_state["lifecycle"]["next_action"] = {"kind": "adjudicate_review_disagreement", "subject_refs": [item.get("id") for item in prior], "preconditions": ["read all reviewer findings", "record evidence-backed decision"], "read_refs": ["contracts/reviewer.md", "references/routing.md"]}
            elif payload.get("verdict") in ("BLOCK", "UNVERIFIABLE"):
                issue_id = append_issue(next_state, {"id": f"review-{digest[:12]}-block", "type": "review_verdict", "cause": "oracle", "impact": "blocking", "affected_refs": [target.get("subject_ref")], "expected": "PASS", "actual": payload.get("verdict"), "disposition": "repair or adjudication required", "resolution_condition": "new evidence or adjudication"}, source_ref=review_id)
                next_state["lifecycle"]["control"] = "BLOCKED"
                next_state["lifecycle"]["reason"] = "review_not_pass"
                next_state["lifecycle"]["issue_refs"] = sorted(set(next_state["lifecycle"].get("issue_refs", []) + [issue_id]))
        evidence = next_state.setdefault("evidence", [])
        if not any(e.get("id") == f"ev-{digest[:16]}" for e in evidence):
            evidence.append({"id": f"ev-{digest[:16]}", "hash": digest, "source": "validated_return", "scenario": args.kind, "outcome": "RETURNED", "observer": "ledger-helper", "subject": args.attempt_id})
        add_usage(next_state.setdefault("usage", default_usage()).setdefault("counters", zero_usage()), {"return_bytes": len(canonical_bytes(payload))})
        next_state["revision"] += 1
        next_state["previous_publication_hash"] = sha256_bytes(previous_raw)
        next_state["updated_at"] = now()
        validate_ledger(next_state, verify_files=False)
        object_store(p, return_raw)
        if integrity_raw is not None and phase_e_review:
            object_store(p, integrity_raw)
        publish(p, next_state, previous_raw)
    return {"ingested": True, "idempotent": False, "attempt_id": args.attempt_id, "return_ref": f"objects/{digest}", "qualification_ref": qualification_ref, "status": "BLOCKED" if write_set_violations else payload.get("status", payload.get("verdict")), "quarantined": bool(write_set_violations), "revision": next_state["revision"]}


def cmd_dispatch(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    packet_path = Path(args.packet).expanduser().resolve()
    packet = read_json(packet_path, "worker/reviewer packet")
    identity = packet_identity(packet)
    if identity.get("ticket_id") != args.ticket_id or identity.get("attempt_id") != args.attempt_id:
        fail("dispatch packet identity does not match ticket/attempt")
    if identity.get("run_id") != args.run_id:
        fail("dispatch packet identity does not match run")
    packet_raw = packet_path.read_bytes()
    packet_kind = packet.get("kind")
    if packet_kind == "worker":
        root = schema()
        validate(packet, root["$defs"][f"{packet_kind}_packet"], root, "$.packet")
        if packet.get("mode") == "repair":
            repair = packet.get("repair")
            if not isinstance(repair, dict):
                fail("repair packet requires a durable repair contract")
            validate(repair, root["$defs"]["repair_contract"], root, "$.packet.repair")
    else:
        fail("dispatch is only for worker packets; reviewer attempts use prepare-review")
    packet_hash = sha256_bytes(packet_raw)
    route = read_json(Path(args.route), "route") if args.route else None
    if route is not None:
        root = schema()
        validate(route, root["$defs"]["route"], root, "$.route")
        validate_route_eligibility(route)
        if route.get("id") not in (None, args.route_id):
            fail("route ID does not match dispatch route-id")
    observed, _ = load_mutation_state(p, args.owner_token)
    if observed["owner"]["token"] != args.owner_token:
        fail("owner token mismatch; stale orchestrator is fenced")
    admit_event(observed, "worker.dispatch")
    observed_ticket = next((item for item in observed.get("tickets", []) if item.get("id") == args.ticket_id), None)
    if observed_ticket is None:
        fail("dispatch references unknown ticket")
    validate_effective_ticket_contract_bindings(
        observed, [observed_ticket], "worker dispatch", require_availability=True,
    )
    if observed.get("lifecycle", {}).get("control") == "BLOCKED" and packet.get("mode") != "repair":
        fail("BLOCKED dispatch requires an explicitly authorized repair packet")
    existing_attempt = next((item for item in observed.get("attempts", []) if item.get("id") == args.attempt_id), None)
    if existing_attempt:
        if existing_attempt.get("packet_hash") == packet_hash and existing_attempt.get("subject_ref") == args.ticket_id and existing_attempt.get("route_ref") == args.route_id:
            validate_execution_binding(
                p, observed, observed_ticket, packet, kind=packet_kind,
                attempt_id=args.attempt_id, packet_hash=packet_hash,
                route_id=args.route_id, route=route, attempt=existing_attempt,
            )
            return {"prepared": True, "idempotent": True, "spawn_disposition": "existing_request_do_not_spawn_again", "spawn_request_id": (existing_attempt.get("runtime") or {}).get("spawn_request_id"), "attempt_id": args.attempt_id, "packet_hash": packet_hash, "revision": observed["revision"]}
        fail("attempt ID already exists with conflicting dispatch")
    def change(state: dict[str, Any]) -> None:
        admit_event(state, "worker.dispatch")
        if state.get("lifecycle", {}).get("control") == "BLOCKED" and packet.get("mode") != "repair":
            fail("BLOCKED dispatch requires an explicitly authorized repair packet")
        ticket = next((t for t in state.get("tickets", []) if t.get("id") == args.ticket_id), None)
        if ticket is None:
            fail("dispatch references unknown ticket")
        validate_effective_ticket_contract_bindings(
            state, [ticket], "worker dispatch", require_availability=True,
        )
        if ticket.get("state") != "READY":
            fail(f"ticket is not READY: {ticket.get('state')}")
        if route:
            validate_route_eligibility(route)
        if identity.get("epoch") != state["owner"]["epoch"]:
            fail("dispatch packet epoch does not match current owner")
        if any(a.get("id") == args.attempt_id for a in state.get("attempts", [])):
            fail("attempt ID already exists")
        if any(t.get("state") in ("RUNNING", "CANDIDATE", "REVIEW") and t.get("id") != args.ticket_id for t in state.get("tickets", [])):
            fail("serial V1 product writer already active")
        execution_binding = validate_execution_binding(
            p, state, ticket, packet, kind=packet_kind,
            attempt_id=args.attempt_id, packet_hash=packet_hash,
            route_id=args.route_id, route=route,
        )
        repair = packet.get("repair")
        repair_plan = None
        attempt_plan = None
        repair_authorization = None
        repair_lease_provenance = None
        binding = current_intent_binding(state) if state.get("intent") else None
        if packet.get("mode") == "repair" and repair:
            refs = repair_finding_refs(repair)
            auths = [active_repair_authorization(state, args.ticket_id, ref) for ref in refs]
            if not refs or not all(auths) or len({item.get("id") for item in auths if item}) != 1:
                signature = repair_signature(repair)
                if any(
                    item.get("subject_ref") == args.ticket_id
                    and item.get("repair_contract")
                    and (item.get("failure_signature") or repair_signature(item["repair_contract"])) == signature
                    for item in state.get("attempts", [])
                ):
                    fail("unchanged repair retry rejected before READY: no causally meaningful change")
                fail("repair dispatch requires one active authorization for the exact ticket and finding set")
            repair_authorization = auths[0]
            canonical_repair, repair_plan, attempt_plan, lease_result = repair_preflight(
                p, state, ticket, repair, packet=packet, route_id=args.route_id, route=route,
                packet_hash=packet_hash, authorization=repair_authorization,
            )
            if not repair_authorization.get("legacy_unbound_attempt_plan") and repair_authorization.get("attempt_plan_ref"):
                stored_attempt_plan = stored_payload(p, repair_authorization.get("attempt_plan_ref"), "authorized AttemptPlan")
                if stored_attempt_plan != attempt_plan:
                    fail("dispatch AttemptPlan differs from the plan approved before ticket READY")
            repair = canonical_repair
            lease_zone, repair_lease_provenance = lease_result
        else:
            lease_zone, repair_lease_provenance = effective_worker_lease(p, state, ticket, packet)
        for dependency in ticket.get("dependency_refs", []):
            dep = next(t for t in state.get("tickets", []) if t["id"] == dependency)
            if dep.get("state") != "INTEGRATED":
                fail(f"dependency is not current INTEGRATED: {dependency}")
        if repair and repair_authorization is None:
            fail("repair worker packet lacks a current repair authorization")
        object_store(p, packet_raw)
        lease = {"id": args.lease_id, "state": "active", "zone": lease_zone}
        attempt_record = {"id": args.attempt_id, "kind": packet.get("kind", "worker"), "mode": packet.get("mode", "implement"), "subject_ref": args.ticket_id, "packet_ref": f"objects/{packet_hash}", "packet_hash": packet_hash, "epoch": state["owner"]["epoch"], "state": "PREPARED", "lease": lease, "route_ref": args.route_id, "checkout": packet.get("workspace", {}).get("root"), "base_sha": packet.get("workspace", {}).get("expected_base"), "candidate_sha": None, "candidate_tree_sha": None, "return_ref": None, "finding_refs": []}
        initialize_attempt_runtime(args.run_id, attempt_record)
        attempt_record["execution_binding"] = execution_binding
        attempt_record["execution_binding_hash"] = sha256_bytes(canonical_bytes(execution_binding))
        if binding:
            attempt_record.update({"intent_revision": binding["revision"], "intent_document_ref": binding["document_ref"], "intent_document_hash": binding["document_hash"]})
        if repair:
            attempt_record["repair_contract"] = repair
            attempt_record["failure_signature"] = repair_signature(repair)
            attempt_record["repair_authorization_ref"] = repair_authorization["id"]
            attempt_record["repair_plan_ref"] = repair_authorization.get("repair_plan_ref")
            if repair_authorization.get("attempt_plan_ref"):
                attempt_record["attempt_plan_ref"] = repair_authorization["attempt_plan_ref"]
            elif attempt_plan is not None:
                attempt_record["attempt_plan_ref"] = f"objects/{object_store(p, canonical_bytes(attempt_plan))}"
            repair_authorization["status"] = "consumed"
            repair_authorization["consumed_by"] = args.attempt_id
        if repair_lease_provenance:
            attempt_record["repair_lease_provenance"] = repair_lease_provenance
        state.setdefault("attempts", []).append(attempt_record)
        add_usage(state.setdefault("usage", default_usage()).setdefault("counters", zero_usage()), {"packet_bytes": len(packet_raw), "attempt_registrations": 1})
        ticket["state"] = "RUNNING"
        ticket["current_attempt"] = args.attempt_id
        if state.get("candidate_model_version") == "1.1":
            ticket["current_worker_attempt"] = args.attempt_id
            ticket["last_worker_attempt"] = args.attempt_id
        if route:
            route_record = dict(route)
            route_record.setdefault("id", args.route_id)
            existing_route = next((item for item in state.get("routes", []) if item.get("id") == args.route_id), None)
            if existing_route is None:
                state.setdefault("routes", []).append(route_record)
            elif existing_route != route_record:
                fail("dispatch route differs from the current published route")
        state["lifecycle"]["next_action"] = {"kind": "await_worker_return", "subject_refs": [args.attempt_id], "preconditions": ["internal orchestration wait; not a user checkpoint", "native child started", "bounded no-progress waits", "return matches packet"], "read_refs": ["contracts/worker.md", "phases/execute.md", "phases/recover.md"]}
    result = transaction(p, args.owner_token, args.revision, change)
    registered = attempt_by_id(result, args.attempt_id)
    return {"prepared": True, "idempotent": False, "spawn_disposition": "register_only_use_spawn_request_id_once", "spawn_request_id": registered["runtime"]["spawn_request_id"], "attempt_id": args.attempt_id, "packet_hash": packet_hash, "revision": result["revision"]}


def cmd_ready_ticket(args: argparse.Namespace) -> dict[str, Any]:
    def change(state: dict[str, Any]) -> None:
        admit_event(state, "ticket.ready")
        if state["lifecycle"]["phase"] != "EXECUTE" or state["lifecycle"]["control"] != "ACTIVE":
            fail("ticket readiness requires ACTIVE EXECUTE")
        publication = current_design_publication(state)
        ticket = next((item for item in state.get("tickets", []) if item.get("id") == args.ticket_id), None)
        if ticket is None or ticket.get("id") not in publication.get("ticket_refs", []):
            fail("ticket is not part of the current design publication")
        if ticket.get("state") != "PLANNED":
            fail(f"ticket readiness requires PLANNED, got {ticket.get('state')}")
        validate_effective_ticket_contract_bindings(
            state, [ticket], "ticket readiness", require_availability=True,
        )
        for dependency in ticket.get("dependency_refs", []):
            dependency_ticket = next(item for item in state.get("tickets", []) if item.get("id") == dependency)
            if dependency_ticket.get("state") != "INTEGRATED":
                fail(f"dependency is not reviewed INTEGRATED: {dependency}")
        active_criteria = {item["id"] for item in state.get("criteria", []) if item.get("status") == "active" and not item.get("invalidated_by")}
        if not ticket.get("criterion_refs") or not set(ticket["criterion_refs"]).issubset(active_criteria):
            fail("ticket readiness requires current criterion bindings")
        ticket["state"] = "READY"
        state["lifecycle"]["next_action"] = {"kind": "dispatch_ticket", "subject_refs": [args.ticket_id], "preconditions": ["fresh packet and attempt", "lease zone available"], "read_refs": ["phases/execute.md", "contracts/worker.md"]}
    result = transaction(paths(args.control_root, args.run_id), args.owner_token, args.revision, change, "ticket-ready")
    return {"ready": True, "ticket_id": args.ticket_id, "revision": result["revision"]}


def cmd_authorize_repair(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    contract = read_json(Path(args.repair_contract).expanduser().resolve(), "repair contract")
    root = schema()
    validate(contract, root["$defs"]["repair_contract"], root, "$.repair_contract")
    finding_refs = repair_finding_refs(contract)
    if args.finding_ref and (len(finding_refs) != 1 or contract.get("finding_ref") != args.finding_ref):
        fail("repair contract finding_ref does not match the command")
    grouped = "finding_refs" in contract
    packet = None
    route = None
    packet_raw = None
    packet_hash = None
    if args.packet:
        packet_path = Path(args.packet).expanduser().resolve()
        packet = read_json(packet_path, "repair worker packet")
        packet_raw = packet_path.read_bytes()
        validate(packet, root["$defs"]["worker_packet"], root, "$.packet")
        if packet.get("mode") != "repair" or packet.get("repair") != contract:
            fail("authorization packet must contain the exact repair contract from --repair-contract")
        packet_identity_value = packet_identity(packet)
        if packet_identity_value.get("run_id") != args.run_id or packet_identity_value.get("ticket_id") != args.ticket_id:
            fail("authorization packet identity does not match run/ticket")
        packet_hash = sha256_bytes(packet_raw)
        if args.route:
            route = read_json(Path(args.route).expanduser().resolve(), "route")
            validate(route, root["$defs"]["route"], root, "$.route")
            validate_route_eligibility(route)
            if route.get("id") not in (None, args.route_id):
                fail("route ID does not match authorization route-id")
    if grouped and (packet is None or not args.route_id):
        fail("grouped RepairPlan authorization requires --packet and --route-id")
    requested_shape = {
        "cause": contract.get("cause"), "finding_refs": sorted(finding_refs),
        "finding_proofs": sorted(repair_proofs(contract), key=lambda item: item["finding_ref"]),
        "stopping_condition": contract.get("stopping_condition"), "causal_change": contract.get("causal_change"),
    }
    observed, _ = load_state(p)
    if observed.get("owner", {}).get("token") != args.owner_token:
        fail("owner token mismatch; stale orchestrator is fenced")
    replay = next((item for item in observed.get("decisions", []) if item.get("id") == args.authorization_id), None)
    if replay is not None:
        if replay.get("type") != "repair_authorization":
            fail("authorization ID already belongs to another decision")
        replay_plan = stored_payload(p, replay.get("repair_plan_ref"), "prior RepairPlan") if replay.get("repair_plan_ref") else None
        replay_shape = {key: replay_plan.get(key) for key in requested_shape} if replay_plan else None
        replay_attempt_plan = stored_payload(p, replay.get("attempt_plan_ref"), "prior AttemptPlan") if replay.get("attempt_plan_ref") else None
        same_attempt_plan = (
            replay_attempt_plan is None and packet is None
            or replay_attempt_plan is not None and packet is not None
            and replay_attempt_plan.get("packet_hash") == packet_hash
            and replay_attempt_plan.get("route_id") == args.route_id
            and replay_attempt_plan.get("route_hash") == (sha256_bytes(canonical_bytes(route)) if route is not None else None)
        )
        if replay_shape == requested_shape and same_attempt_plan:
            return {"authorized": True, "idempotent": True, "authorization_id": args.authorization_id, "ticket_id": args.ticket_id, "finding_refs": sorted(finding_refs), "revision": observed["revision"]}
        fail("authorization ID already exists with a different canonical RepairPlan/AttemptPlan")

    def change(state: dict[str, Any]) -> None:
        admit_event(state, "repair.authorize")
        ticket = next((item for item in state.get("tickets", []) if item.get("id") == args.ticket_id), None)
        existing_id = next((item for item in state.get("decisions", []) if item.get("id") == args.authorization_id), None)
        if existing_id is not None:
            if existing_id.get("type") != "repair_authorization":
                fail("authorization ID already belongs to another decision")
            prior_plan = stored_payload(p, existing_id.get("repair_plan_ref"), "prior RepairPlan") if existing_id.get("repair_plan_ref") else None
            prior_shape = {key: prior_plan.get(key) for key in requested_shape} if prior_plan else None
            same_attempt_plan = True
            if packet is not None:
                prior_attempt_plan = stored_payload(p, existing_id.get("attempt_plan_ref"), "prior AttemptPlan") if existing_id.get("attempt_plan_ref") else None
                same_attempt_plan = bool(prior_attempt_plan and prior_attempt_plan.get("packet_hash") == packet_hash and prior_attempt_plan.get("route_id") == args.route_id)
            elif existing_id.get("attempt_plan_ref"):
                same_attempt_plan = False
            if prior_shape == requested_shape and same_attempt_plan:
                raise IdempotentResult({"authorized": True, "idempotent": True, "authorization_id": args.authorization_id, "ticket_id": args.ticket_id, "finding_refs": sorted(finding_refs), "revision": state["revision"]})
            fail("authorization ID already exists with a different canonical RepairPlan/AttemptPlan")
        if ticket is None:
            fail("repair authorization requires a REVIEW/BLOCKED/REPAIR ticket")
        prior_unused = [
            item for item in state.get("decisions", [])
            if item.get("type") == "repair_authorization" and item.get("status") == "authorized"
            and ticket["id"] in item.get("affected_refs", [])
            and set(finding_refs) & set(item.get("affected_refs", []))
            and not any(attempt.get("repair_authorization_ref") == item.get("id") for attempt in state.get("attempts", []))
        ]
        if ticket.get("state") not in ("REVIEW", "BLOCKED", "REPAIR") and not (ticket.get("state") == "READY" and prior_unused):
            fail("repair authorization requires a REVIEW/BLOCKED/REPAIR ticket or an unused READY authorization")
        canonical, repair_plan, attempt_plan, lease_result = repair_preflight(
            p, state, ticket, contract, packet=packet, route_id=args.route_id,
            route=route, packet_hash=packet_hash,
        )
        projection = finding_obligation_projection(state)
        for previous in state.get("decisions", []):
            if previous.get("type") != "repair_authorization" or previous.get("status") != "authorized":
                continue
            if ticket["id"] not in previous.get("affected_refs", []) or not (set(finding_refs) & set(previous.get("affected_refs", []))):
                continue
            if any(item.get("repair_authorization_ref") == previous.get("id") for item in state.get("attempts", [])):
                fail("consumed repair authorization cannot be replaced")
            previous["status"] = "superseded"
            previous["superseded_by"] = args.authorization_id
            previous.setdefault("invalidated_by", [])
            if args.authorization_id not in previous["invalidated_by"]:
                previous["invalidated_by"].append(args.authorization_id)
        continuation_blocker_refs = {
            decision.get("blocker_ref")
            for decision in state.get("decisions", [])
            if decision.get("type") == "continuation_candidate_authorization"
            and decision.get("status") == "applied"
            and args.ticket_id in decision.get("affected_refs", [])
        }
        preserve_blocked_control = bool(
            state["lifecycle"].get("control") == "BLOCKED"
            and continuation_blocker_refs
            and any(
                issue.get("id") in continuation_blocker_refs
                and issue.get("impact") == "blocking"
                and not issue.get("invalidated_by")
                for issue in state.get("issues", [])
            )
        )
        selected_refs = set(repair_plan["finding_refs"])
        unrelated_blockers = [
            item for item in state.get("issues", [])
            if item.get("impact") == "blocking"
            and not item.get("invalidated_by")
            and item.get("id") not in selected_refs
            and item.get("finding_ref") not in selected_refs
        ]
        unrelated_obligations = [
            item for item in projection["obligations"]
            if item.get("status") != "closed" and item.get("finding_ref") not in selected_refs
        ]
        preserve_blocked_control = preserve_blocked_control or bool(unrelated_blockers or unrelated_obligations)
        for attempt in state.get("attempts", []):
            if attempt.get("subject_ref") == args.ticket_id and attempt.get("state") in ("PREPARED", "DISPATCHED"):
                fail("repair authorization requires stopped attempts")
            if attempt.get("subject_ref") == args.ticket_id and attempt.get("lease", {}).get("state") == "quarantined":
                fail("repair authorization requires quarantine reconciliation")
            if attempt.get("subject_ref") == args.ticket_id and attempt.get("lease", {}).get("state") == "active":
                require_runtime_stopped(p, attempt, "repair lease release/reuse")
                attempt["lease"]["state"] = "released"
        repair_plan_ref = f"objects/{object_store(p, canonical_bytes(repair_plan))}"
        attempt_plan_ref = f"objects/{object_store(p, canonical_bytes(attempt_plan))}" if attempt_plan is not None else None
        evidence_refs = [*repair_plan["finding_refs"], repair_plan_ref]
        if attempt_plan_ref:
            evidence_refs.append(attempt_plan_ref)
        state.setdefault("decisions", []).append({
            "id": args.authorization_id, "type": "repair_authorization", "status": "authorized", "decision": "REPAIR",
            "reason": repair_plan["finding_proofs"][0]["hypothesis"], "evidence_refs": evidence_refs,
            "affected_refs": [args.ticket_id, *repair_plan["finding_refs"]], "candidate_ref": repair_plan["source_candidate_ref"],
            "repair_plan_ref": repair_plan_ref, "attempt_plan_ref": attempt_plan_ref,
            "legacy_unbound_attempt_plan": attempt_plan is None,
            "supersedes": [item.get("id") for item in state.get("decisions", []) if item.get("type") == "repair_authorization" and item.get("superseded_by") == args.authorization_id],
            "intent_revision": state.get("intent", {}).get("current_revision"), "invalidated_by": [],
        })
        for finding in state.get("findings", []):
            if finding.get("id") in selected_refs:
                finding["repair_contract_ref"] = args.authorization_id
        ticket["state"] = "READY"
        if preserve_blocked_control:
            state["lifecycle"]["next_action"] = {"kind": "dispatch_repair_with_blocker_retained", "subject_refs": [args.ticket_id, *repair_plan["finding_refs"], *sorted(continuation_blocker_refs)], "preconditions": ["owner-authorized candidate-bound repair", "external/out-of-scope blocker remains unresolved", "do not widen the ticket lease"], "read_refs": ["phases/execute.md", "references/routing.md"]}
        else:
            state["lifecycle"]["control"] = "ACTIVE"
            state["lifecycle"]["reason"] = "repair_authorized"
            state["lifecycle"]["next_action"] = {"kind": "dispatch_repair", "subject_refs": [args.ticket_id, *repair_plan["finding_refs"]], "preconditions": ["preflighted AttemptPlan", "dependencies remain INTEGRATED"], "read_refs": ["phases/execute.md", "references/routing.md"]}

    try:
        result = transaction(p, args.owner_token, args.revision, change, "repair-authorized")
    except IdempotentResult as prior:
        return prior.result
    return {"authorized": True, "idempotent": False, "authorization_id": args.authorization_id, "ticket_id": args.ticket_id, "finding_refs": sorted(finding_refs), "revision": result["revision"]}


def cmd_revoke_repair(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    reason = nonempty_string(args.reason, "revocation reason")
    observed, _ = load_state(p)
    if observed.get("owner", {}).get("token") != args.owner_token:
        fail("owner token mismatch; stale orchestrator is fenced")
    prior_event = next((item for item in observed.get("decisions", []) if item.get("id") == args.revocation_id), None)
    if prior_event is not None:
        if prior_event.get("type") == "repair_authorization_lifecycle" and prior_event.get("decision") == "REVOKE" and prior_event.get("affected_refs") == [args.authorization_id] and prior_event.get("reason") == reason:
            return {"revoked": True, "idempotent": True, "authorization_id": args.authorization_id, "revocation_id": args.revocation_id, "revision": observed["revision"]}
        fail("revocation ID already exists with conflicting lifecycle evidence")

    def change(state: dict[str, Any]) -> None:
        admit_event(state, "repair.authorize")
        prior_event = next((item for item in state.get("decisions", []) if item.get("id") == args.revocation_id), None)
        authorization = next((item for item in state.get("decisions", []) if item.get("id") == args.authorization_id), None)
        if prior_event is not None:
            if prior_event.get("type") == "repair_authorization_lifecycle" and prior_event.get("decision") == "REVOKE" and prior_event.get("affected_refs") == [args.authorization_id] and prior_event.get("reason") == reason:
                raise IdempotentResult({"revoked": True, "idempotent": True, "authorization_id": args.authorization_id, "revocation_id": args.revocation_id, "revision": state["revision"]})
            fail("revocation ID already exists with conflicting lifecycle evidence")
        if authorization is None or authorization.get("type") != "repair_authorization":
            fail("unknown repair authorization")
        if authorization.get("status") != "authorized":
            fail("only an unused authorized repair may be revoked")
        if any(item.get("repair_authorization_ref") == authorization.get("id") for item in state.get("attempts", [])):
            fail("consumed repair authorization cannot be revoked")
        authorization["status"] = "revoked"
        authorization["revoked_by"] = args.revocation_id
        authorization["revocation_reason"] = reason
        state.setdefault("decisions", []).append({
            "id": args.revocation_id, "type": "repair_authorization_lifecycle", "status": "applied",
            "decision": "REVOKE", "reason": reason, "evidence_refs": [args.authorization_id],
            "affected_refs": [args.authorization_id], "invalidated_by": [],
        })
    try:
        result = transaction(p, args.owner_token, args.revision, change, "repair-revoked")
    except IdempotentResult as prior:
        return prior.result
    return {"revoked": True, "idempotent": False, "authorization_id": args.authorization_id, "revocation_id": args.revocation_id, "revision": result["revision"]}


def cmd_terminate_attempt(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    evidence_path = Path(args.evidence).expanduser().resolve()
    evidence = read_json(evidence_path, "attempt termination evidence")
    evidence_raw = evidence_path.read_bytes()
    evidence_digest = sha256_bytes(evidence_raw)
    if args.lease_state == "released":
        typed_runtime_stop = bool(
            evidence.get("kind") == "runtime_observation"
            and evidence.get("event") in ("stop", "not_started")
            and (evidence.get("event") != "stop" or evidence.get("coverage", {}).get("descendant_writers") == "included")
        )
        if not typed_runtime_stop and (evidence.get("status") != "PASS" or evidence.get("writer_stopped") is not True):
            fail("lease release requires an exact runtime stop/not_started receipt or PASS writer_stopped evidence")

    def change(state: dict[str, Any]) -> None:
        admit_event(state, "attempt.reconcile")
        attempt = attempt_by_id(state, args.attempt_id)
        if attempt.get("state") not in ("PREPARED", "DISPATCHED"):
            fail("only an in-flight attempt may be terminated")
        if attempt.get("epoch") != state["owner"]["epoch"] and args.lease_state == "released":
            fail("stale-epoch attempt may only be quarantined until takeover reconciliation")
        if args.lease_state == "released" and isinstance(attempt.get("runtime"), dict):
            require_runtime_stopped(p, attempt, "runtime reservation release")
            runtime = attempt["runtime"]
            exact_stop_ref = runtime.get("stop_ref") if runtime_liveness(attempt) == "stopped" else runtime.get("not_started_ref")
            if exact_stop_ref != f"objects/{evidence_digest}":
                fail("runtime reservation release evidence must be the exact registered stop/not_started receipt")
        object_store(p, evidence_raw)
        evidence_ref = f"objects/{evidence_digest}"
        attempt["state"] = args.state
        attempt["lease"]["state"] = args.lease_state
        attempt["termination_evidence_ref"] = evidence_ref
        ticket = next((item for item in state.get("tickets", []) if item.get("current_attempt") == args.attempt_id), None)
        if ticket and ticket.get("state") not in ("INTEGRATED", "CANCELLED", "STALE"):
            ticket["state"] = "BLOCKED"
        if ticket and ticket.get("current_worker_attempt") == args.attempt_id:
            ticket["current_worker_attempt"] = None
        ev_id = f"ev-{evidence_digest[:16]}"
        if ev_id not in {item.get("id") for item in state.get("evidence", [])}:
            state.setdefault("evidence", []).append({"id": ev_id, "hash": evidence_digest, "source": "attempt_termination", "scenario": args.state, "outcome": args.lease_state, "observer": "ledger-helper", "subject": args.attempt_id})
        issue_id = append_issue(state, {"id": f"attempt-{args.attempt_id}-{args.state.lower()}", "type": "attempt_termination", "cause": "orchestration", "impact": "blocking", "affected_refs": [args.attempt_id, *([ticket["id"]] if ticket else [])], "expected": "bounded attempt returns or is stopped with evidence", "actual": args.state, "disposition": "recover/retry with a fresh attempt after lease reconciliation", "resolution_condition": "released lease and fresh attempt"}, source_ref=args.attempt_id)
        state["lifecycle"]["control"] = "BLOCKED"
        state["lifecycle"]["reason"] = f"attempt_{args.state.lower()}"
        state["lifecycle"]["issue_refs"] = sorted(set(state["lifecycle"].get("issue_refs", []) + [issue_id]))
        state["lifecycle"]["next_action"] = {"kind": "recover_attempt", "subject_refs": [args.attempt_id], "preconditions": ["lease released or quarantine reconciled", "fresh attempt ID"], "read_refs": ["phases/recover.md", "references/ledger.md"]}

    result = transaction(p, args.owner_token, args.revision, change, "attempt-terminated")
    return {"terminated": True, "attempt_id": args.attempt_id, "state": args.state, "lease_state": args.lease_state, "evidence_ref": f"objects/{evidence_digest}", "revision": result["revision"]}


def cmd_observe_runtime(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    receipt_path = Path(args.event_file).expanduser().resolve()
    regular_non_symlink(receipt_path)
    raw = receipt_path.read_bytes()
    if len(raw) > 64 * 1024:
        fail("runtime observation exceeds the 64 KiB contract bound")
    try:
        receipt = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        fail(f"runtime observation is not valid JSON: {exc}")
    root = schema()
    validate(receipt, root["$defs"]["runtime_observation"], root, "$.runtime_observation")
    digest = sha256_bytes(raw)
    ref = f"objects/{digest}"

    # Exact byte replay remains a no-op even after unrelated downstream progress.
    with Lock(p["lock"]):
        observed, _ = load_state(p)
        if observed.get("owner", {}).get("token") != args.owner_token:
            fail("owner token mismatch; stale orchestrator is fenced")
        attempt = attempt_by_id(observed, args.attempt_id)
        runtime = attempt.get("runtime")
        if not isinstance(runtime, dict):
            fail("attempt has no runtime protocol record; legacy liveness remains unknown")
        if receipt.get("event_id") != args.event_id or receipt.get("event") != args.event:
            fail("runtime observation event ID/type does not match command arguments")
        expected = {
            "run_id": args.run_id, "attempt_id": args.attempt_id, "epoch": attempt.get("epoch"),
            "packet_hash": attempt.get("packet_hash"), "spawn_request_id": runtime.get("spawn_request_id"),
        }
        for field, value in expected.items():
            if receipt.get(field) != value:
                fail(f"runtime observation {field} does not exactly match registered attempt")
        if ref in runtime.get("observation_refs", []):
            disposition = "already_observed; do_not_spawn_again" if receipt["event"] == "start" else "already_observed"
            return {"observed": True, "idempotent": True, "disposition": disposition, "attempt_id": args.attempt_id, "event": args.event, "observation_ref": ref, "liveness": runtime_liveness(attempt), "revision": observed["revision"]}
        if any(
            stored_payload(p, prior_ref, "runtime observation").get("event_id") == receipt["event_id"]
            for prior_ref in runtime.get("observation_refs", [])
        ):
            fail("runtime observation event_id is already bound to different immutable bytes")
        if observed.get("revision") != args.revision:
            fail(f"revision mismatch: expected {args.revision}, current {observed['revision']}")

    def change(state: dict[str, Any]) -> None:
        admit_event(state, "attempt.reconcile")
        attempt = attempt_by_id(state, args.attempt_id)
        runtime = attempt.get("runtime")
        if not isinstance(runtime, dict):
            fail("attempt has no runtime protocol record; legacy liveness remains unknown")
        for field, value in expected.items():
            if receipt.get(field) != value:
                fail(f"runtime observation {field} does not exactly match registered attempt")
        if receipt.get("event_id") != args.event_id or receipt.get("event") != args.event:
            fail("runtime observation event ID/type does not match command arguments")
        liveness = runtime_liveness(attempt)
        event = receipt["event"]
        if event == "start":
            if attempt.get("state") not in ("PREPARED", "DISPATCHED"):
                fail("start observation is only valid for a prepared/dispatched attempt")
            if liveness != "unknown" or runtime.get("runtime_instance_id") or runtime.get("start_ref") or runtime.get("not_started_ref") or runtime.get("return_observation_ref"):
                fail("start observation is valid only once for an unknown, unstarted spawn request")
            if not receipt.get("runtime_instance_id"):
                fail("start observation requires a runtime instance ID")
            runtime["runtime_instance_id"] = receipt["runtime_instance_id"]
            runtime["liveness"] = "running"
            runtime["start_ref"] = ref
            add_usage(state.setdefault("usage", default_usage()).setdefault("counters", zero_usage()), {"spawn_calls": 1})
        elif event == "heartbeat":
            if liveness != "running" or receipt.get("runtime_instance_id") != runtime.get("runtime_instance_id"):
                fail("heartbeat must be bound to the exact currently running runtime instance")
        elif event == "return_observed":
            if liveness == "not_started":
                fail("return observation conflicts with a proven not_started request")
            if runtime.get("return_observation_ref"):
                fail("attempt already has a return observation; conflicting observations are immutable")
            if not receipt.get("runtime_instance_id"):
                fail("return_observed requires the exact runtime instance ID")
            if runtime.get("runtime_instance_id") and receipt.get("runtime_instance_id") != runtime.get("runtime_instance_id"):
                fail("return observation does not match the registered runtime instance")
            if not receipt.get("return_hash"):
                fail("return_observed requires the immutable return payload hash")
            if attempt.get("return_ref") and attempt.get("return_ref") != f"objects/{receipt['return_hash']}":
                fail("return_observed hash conflicts with the already ingested return bytes")
            runtime["runtime_instance_id"] = receipt["runtime_instance_id"]
        elif event == "stop":
            if liveness == "running":
                if receipt.get("runtime_instance_id") != runtime.get("runtime_instance_id"):
                    fail("stop observation must be bound to the exact running runtime instance")
            elif liveness == "unknown" and not runtime.get("runtime_instance_id"):
                if not receipt.get("runtime_instance_id"):
                    fail("late stop observation requires the exact runtime instance ID")
                runtime["runtime_instance_id"] = receipt["runtime_instance_id"]
            elif liveness == "unknown" and receipt.get("runtime_instance_id") == runtime.get("runtime_instance_id"):
                pass
            elif liveness == "unknown" and runtime.get("runtime_instance_id"):
                fail("late stop observation must match the exact runtime instance already observed for this spawn request")
            else:
                fail("stop observation is valid only for a running or unresolved runtime request")
            if receipt.get("coverage", {}).get("descendant_writers") != "included":
                fail("stop observation must cover descendant writers")
        elif event == "not_started":
            if attempt.get("state") not in ("PREPARED", "DISPATCHED"):
                fail("not_started observation is only valid for a prepared/dispatched attempt")
            if liveness != "unknown" or runtime.get("start_ref") or runtime.get("return_observation_ref"):
                fail("not_started is valid only when no start or runtime return was observed")
            if receipt.get("runtime_instance_id") is not None:
                fail("not_started observation must not name a runtime instance")
        else:
            fail(f"unsupported runtime observation event: {event}")
        object_store(p, raw)
        runtime.setdefault("observation_refs", []).append(ref)
        if event == "heartbeat":
            runtime.setdefault("heartbeat_refs", []).append(ref)
        elif event == "return_observed":
            runtime["return_observation_ref"] = ref
        elif event == "stop":
            runtime["liveness"] = "stopped"
            runtime["stop_ref"] = ref
            if attempt.get("kind") == "review" and attempt.get("state") == "RETURNED":
                attempt.setdefault("lease", {})["state"] = "released"
        elif event == "not_started":
            runtime["liveness"] = "not_started"
            runtime["not_started_ref"] = ref

    result = transaction(p, args.owner_token, args.revision, change, "runtime-observed")
    return {
        "observed": True, "idempotent": False,
        "disposition": "spawn_observed_once; do_not_repeat_spawn" if args.event == "start" else "recorded_no_liveness_inference",
        "attempt_id": args.attempt_id, "event": args.event, "observation_ref": ref,
        "liveness": runtime_liveness(attempt_by_id(result, args.attempt_id)), "revision": result["revision"],
    }


def cmd_candidate(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    observed, _ = load_mutation_state(p, args.owner_token)
    if observed["owner"]["token"] != args.owner_token:
        fail("owner token mismatch; stale orchestrator is fenced")
    observed_attempt = attempt_by_id(observed, args.attempt_id)
    admit_event(observed, "candidate.publish")
    observed_ticket = next((item for item in observed.get("tickets", []) if item.get("id") == observed_attempt.get("subject_ref")), None)
    observed_candidate = current_candidate_record(observed, observed_ticket) if observed_ticket else None
    observed_producer = current_candidate_producer(observed, observed_ticket) if observed_ticket else None
    already_published = bool(
        observed_candidate and observed_candidate.get("quality") == "DONE"
        and observed_producer and observed_producer.get("id") == args.attempt_id
    )
    if not already_published:
        if observed_attempt.get("state") != "RETURNED":
            fail("candidate requires a validated RETURNED worker attempt")
        if observed_attempt.get("kind") != "worker":
            fail("candidate requires a worker attempt")
        require_runtime_stopped(p, observed_attempt, "candidate qualification")
        if observed_attempt.get("lease", {}).get("state") != "active":
            fail("candidate requires an active, non-quarantined worker lease")
        observed_return = stored_payload(p, observed_attempt.get("return_ref"), "worker return")
        if observed_return.get("status") != "DONE":
            fail("only a semantically complete worker DONE return may become a candidate; BLOCKED/FAILED/HANDOFF are durable non-candidate outcomes")
    observed_operation = next((item for item in observed.get("operations", []) if item.get("id") == args.operation_id), None)
    if observed_operation is None:
        fail("candidate requires a durable candidate_commit operation")
    supplied_raw: bytes | None = None
    if args.commit_receipt:
        supplied_path = Path(args.commit_receipt).expanduser().resolve()
        regular_non_symlink(supplied_path)
        supplied_raw = supplied_path.read_bytes()
        receipt = read_json(supplied_path, "Git candidate receipt")
    elif observed_operation.get("state") in ("applied", "finalized"):
        receipt_ref = observed_operation.get("receipt_ref")
        receipt = stored_payload(p, receipt_ref, "applied candidate effect receipt")
        digest_match = re.fullmatch(r"objects/([0-9a-f]{64})", receipt_ref or "")
        if digest_match is None:
            fail("applied candidate effect has no immutable receipt; it cannot be adopted")
        receipt_path = p["objects"] / digest_match.group(1)
        regular_non_symlink(receipt_path)
        supplied_raw = receipt_path.read_bytes()
        if sha256_bytes(supplied_raw) != digest_match.group(1):
            fail("applied candidate receipt hash does not match its immutable reference")
    else:
        fail("prepared candidate publication requires the exact commit receipt")
    if receipt.get("status") != "PASS" or not GIT_SHA_RE.fullmatch(receipt.get("commit_sha", "")) or not GIT_SHA_RE.fullmatch(receipt.get("tree_sha", "")):
        fail("candidate requires PASS receipt with commit_sha and tree_sha")
    if supplied_raw is None:
        fail("candidate receipt bytes are unavailable")
    supplied_receipt_hash = sha256_bytes(supplied_raw)
    if observed_operation.get("state") in ("applied", "finalized"):
        stored_ref = observed_operation.get("receipt_ref")
        if stored_ref != f"objects/{supplied_receipt_hash}":
            fail("candidate adoption receipt differs from the immutable applied-effect receipt")
    if (
        observed_candidate and observed_candidate.get("quality") == "DONE"
        and observed_producer and observed_producer.get("id") == args.attempt_id
        and observed_candidate.get("sha") == receipt["commit_sha"]
        and observed_candidate.get("tree_sha") == receipt["tree_sha"]
        and observed_candidate.get("proof_ref") == observed_attempt.get("candidate_proof_ref")
        and observed_operation.get("state") == "finalized"
        and observed_operation.get("proof_ref") == observed_attempt.get("candidate_proof_ref")
        and observed_ticket and observed_ticket.get("state") in ("CANDIDATE", "REVIEW", "INTEGRATED")
    ):
        proof = verify_verified_candidate_proof(p, observed_operation["proof_ref"])
        if proof.get("candidate_sha") != receipt["commit_sha"] or proof.get("operation_id") != args.operation_id:
            fail("finalized candidate proof does not match the exact replay")
        return {"candidate": receipt["commit_sha"], "proof_ref": observed_operation["proof_ref"], "idempotent": True, "revision": observed["revision"], "next_action": observed["lifecycle"]["next_action"]}
    if observed_operation.get("state") == "finalized":
        fail("candidate operation was finalized with a different candidate proof")
    def change(state: dict[str, Any]) -> None:
        admit_event(state, "candidate.publish")
        control = state.get("lifecycle", {}).get("control")
        attempt = attempt_by_id(state, args.attempt_id)
        if attempt["state"] != "RETURNED":
            fail("candidate requires a validated RETURNED worker attempt")
        if attempt.get("kind") != "worker":
            fail("candidate requires a worker attempt")
        require_runtime_stopped(p, attempt, "candidate qualification")
        if attempt.get("lease", {}).get("state") != "active":
            fail("candidate requires an active, non-quarantined worker lease")
        worker_return = stored_payload(p, attempt.get("return_ref"), "worker return")
        if worker_return.get("status") != "DONE":
            fail("only a semantically complete worker DONE return may become a candidate; BLOCKED/FAILED/HANDOFF are durable non-candidate outcomes")
        effect_recovery_adoption = bool(
            control == "BLOCKED"
            and state.get("lifecycle", {}).get("reason") == "uncertain_effect_requires_authority_resolution"
            and (operation_for_recovery := next((item for item in state.get("operations", []) if item.get("id") == args.operation_id), None))
            and operation_for_recovery.get("state") == "applied"
        )
        if control == "BLOCKED" and not effect_recovery_adoption:
            blocked_attempt = attempt
            blocked_ticket = next((item for item in state.get("tickets", []) if blocked_attempt and item.get("id") == blocked_attempt.get("subject_ref")), None)
            blocked_operation = next((item for item in state.get("operations", []) if item.get("id") == args.operation_id), None)
            repair_contract = blocked_attempt.get("repair_contract") if blocked_attempt else None
            repair_finding_refs_value = repair_finding_refs(repair_contract) if isinstance(repair_contract, dict) else []
            authorization = repair_authorization_for_attempt(state, blocked_ticket.get("id"), repair_contract, blocked_attempt.get("id")) if blocked_ticket and repair_finding_refs_value else None
            same_checkout = bool(
                blocked_attempt and isinstance(blocked_attempt.get("checkout"), str) and blocked_attempt.get("checkout")
                and blocked_operation and isinstance(blocked_operation.get("target"), str) and blocked_operation.get("target")
                and isinstance(receipt.get("checkout"), str) and receipt.get("checkout")
                and Path(blocked_attempt["checkout"]).expanduser().resolve() == Path(blocked_operation["target"]).expanduser().resolve()
                and Path(blocked_attempt["checkout"]).expanduser().resolve() == Path(receipt["checkout"]).expanduser().resolve()
            )
            exact_blocked_repair = bool(
                blocked_attempt and blocked_ticket and blocked_operation and authorization
                and blocked_attempt.get("kind") == "worker"
                and blocked_attempt.get("mode") == "repair"
                and blocked_attempt.get("state") == "RETURNED"
                and blocked_attempt.get("repair_authorization_ref") == authorization.get("id")
                and blocked_attempt.get("candidate_sha") is None
                and blocked_ticket.get("current_attempt") == blocked_attempt.get("id")
                and blocked_ticket.get("last_worker_attempt") == blocked_attempt.get("id")
                and blocked_ticket.get("current_worker_attempt") is None
                and blocked_operation.get("kind") == "candidate_commit"
                and blocked_operation.get("state") in ("prepared", "applied")
                and blocked_operation.get("authority_ref") == authorization.get("id")
                and blocked_operation.get("expected_before") == blocked_attempt.get("base_sha")
                and blocked_operation.get("intended_after") in (None, receipt.get("commit_sha"))
                and receipt.get("authority_ref") == authorization.get("id")
                and receipt.get("base_sha") == blocked_attempt.get("base_sha")
                and same_checkout
            )
            if not exact_blocked_repair:
                fail("BLOCKED candidate publication requires the exact current authorized repair worker and prepared candidate_commit proof")
        elif control != "ACTIVE" and not effect_recovery_adoption:
            fail("ordinary candidate publication requires ACTIVE control")
        if receipt.get("base_sha") and attempt.get("base_sha") and receipt["base_sha"] != attempt["base_sha"]:
            fail("candidate base SHA mismatch")
        operation = next((item for item in state.get("operations", []) if item.get("id") == args.operation_id), None)
        if operation is None:
            fail("candidate requires the exact durable candidate_commit operation")
        if operation.get("kind") != "candidate_commit":
            fail("candidate requires a candidate_commit operation")
        if operation.get("state") not in ("prepared", "applied"):
            fail("candidate operation is not adoptable from prepared/applied state")
        if operation.get("state") == "applied" and operation.get("receipt_ref") != f"objects/{supplied_receipt_hash}":
            fail("applied candidate effect receipt differs from its immutable journal receipt")
        ticket = next((t for t in state.get("tickets", []) if t.get("id") == attempt.get("subject_ref")), None)
        if ticket is None:
            fail("candidate attempt has no same-ticket candidate target")
        parent_candidate_ref = ticket.get("current_candidate")
        proof, proof_ref = build_verified_candidate_proof(
            p, state, ticket, attempt, operation, args.operation_id, receipt, supplied_raw,
            quality="DONE", parent_candidate_ref=parent_candidate_ref,
        )
        attempt["candidate_sha"] = receipt["commit_sha"]
        attempt["candidate_tree_sha"] = receipt["tree_sha"]
        attempt["candidate_proof_ref"] = proof_ref
        attempt["state"] = "RETURNED"
        ticket["state"] = "CANDIDATE"
        publish_candidate_projection(state, ticket, attempt, quality="DONE", proof_ref=proof_ref)
        if operation.get("state") == "prepared":
            transition_effect(operation, "applied")
        transition_effect(operation, "finalized")
        operation["target"] = proof["target"]
        operation["expected_before"] = proof["base_sha"]
        operation["intended_after"] = proof["candidate_sha"]
        operation["receipt_ref"] = proof["commit_receipt_ref"]
        operation["proof_ref"] = proof_ref
        operation["candidate_ref"] = f"candidate-{attempt['id']}"
        operation["finalized_revision"] = state["revision"] + 1
        if state.get("lifecycle", {}).get("control") == "BLOCKED" and state.get("lifecycle", {}).get("reason") == "uncertain_effect_requires_authority_resolution":
            other_unresolved_effects = [
                item for item in state.get("operations", [])
                if item.get("id") != operation.get("id") and item.get("state") in ("prepared", "uncertain", "applied")
            ]
            blocking_issues = [item for item in state.get("issues", []) if item.get("impact") == "blocking" and not item.get("invalidated_by")]
            if not other_unresolved_effects and not blocking_issues:
                state["lifecycle"]["control"] = "ACTIVE"
                state["lifecycle"]["reason"] = None
        state["lifecycle"]["next_action"] = {"kind": "review_change", "subject_refs": [args.attempt_id], "preconditions": ["candidate SHA frozen", "integrity baseline recorded"], "read_refs": ["contracts/reviewer.md", "references/safety.md"]}
    result = transaction(p, args.owner_token, args.revision, change)
    return {"candidate": receipt["commit_sha"], "proof_ref": attempt_by_id(result, args.attempt_id).get("candidate_proof_ref"), "idempotent": False, "revision": result["revision"], "next_action": result["lifecycle"]["next_action"]}


def validate_continuation_provenance(
    p: dict[str, Path], state: dict[str, Any], ticket: dict[str, Any], attempt: dict[str, Any], packet: dict[str, Any]
) -> None:
    """Revalidate the attempt's ticket lease and repair lineage before preservation."""
    requested = packet_write_zone(packet)
    denied = [relative_path(item, "packet write deny path").rstrip("/") for item in packet.get("write", {}).get("deny", [])]
    if any(
        entry["path"] == path or entry["path"].startswith(path + "/") or path.startswith(entry["path"] + "/")
        for entry in requested for path in denied
    ):
        fail("continuation packet write allowlist conflicts with its deny list")
    disallowed = [
        {"path": entry["path"], "operation": operation}
        for entry in requested
        for operation in entry["operations"]
        if not zone_allows(ticket.get("zone", []), entry["path"], operation)
    ]
    stored_zone = attempt.get("lease", {}).get("zone", [])
    if attempt.get("mode") != "repair":
        if packet.get("repair") or attempt.get("repair_lease_provenance"):
            fail("non-repair continuation attempt contains repair provenance")
        if stored_zone != requested or disallowed:
            fail("continuation attempt lease does not exactly match the ticket-authorized packet allowlist")
        return

    packet_repair = packet.get("repair")
    if not isinstance(packet_repair, dict):
        fail("continuation repair packet has no durable repair contract")
    legacy_plan = False
    if current_candidate_record(state, ticket) is None and not attempt.get("repair_plan_ref"):
        # Compatibility for pre-1.1 attempts whose only candidate pointer is an older worker attempt.
        repair = packet_repair
        repair_plan = None
        legacy_plan = attempt.get("repair_contract") == packet_repair
    else:
        repair, repair_plan = normalize_repair_contract(state, ticket, packet_repair)
        if attempt.get("repair_contract") != repair or attempt.get("repair_plan_ref") is None:
            fail("continuation repair packet does not match the attempt's stored repair contract")
    if not legacy_plan:
        candidate = current_candidate_record(state, ticket)
        if candidate is None or attempt.get("base_sha") != candidate.get("sha"):
            fail("continuation repair source candidate is no longer current")
    authorization_ref = attempt.get("repair_authorization_ref")
    authorization = repair_authorization_for_attempt(state, ticket["id"], repair, attempt["id"])
    if authorization and authorization.get("id") != authorization_ref:
        authorization = None
    if authorization is None:
        fail("continuation repair attempt has no current same-ticket repair authorization")
    authorized_plan = stored_payload(p, authorization.get("repair_plan_ref"), "authorized RepairPlan") if authorization.get("repair_plan_ref") else None
    if legacy_plan:
        legacy_refs = [ref for ref in authorization.get("evidence_refs", []) if isinstance(ref, str) and ref.startswith("objects/")]
        if len(legacy_refs) != 1 or stored_payload(p, legacy_refs[0], "legacy authorized repair contract") != repair:
            fail("legacy continuation repair authorization is not bound to the exact repair contract")
    elif authorized_plan != repair_plan:
        fail("continuation repair authorization is not bound to the exact repair contract")
    source_ref = repair.get("source_attempt_ref")
    base_sha = attempt.get("base_sha")
    source = next((item for item in state.get("attempts", []) if item.get("id") == source_ref), None)
    if (
        source is None
        or source.get("kind") != "worker"
        or source.get("subject_ref") != ticket.get("id")
        or source.get("state") != "RETURNED"
        or source.get("candidate_sha") != base_sha
        or source.get("lease", {}).get("state") == "quarantined"
    ):
        fail("continuation repair source is missing, foreign, stale, or quarantined")
    validated_candidate_worker_return(p, state, ticket, source)
    if any(not finding_matches_candidate(state, ref, ticket["id"], base_sha) for ref in repair_finding_refs(repair)):
        fail("continuation repair finding set is not bound to the exact same-ticket source candidate")

    provenance = attempt.get("repair_lease_provenance")
    if not disallowed:
        if stored_zone != requested or provenance is not None:
            fail("continuation repair lease or provenance differs from its unexpanded packet allowlist")
        return
    if not isinstance(provenance, dict):
        fail("continuation repair is missing its required lease provenance")
    if (
        provenance.get("authorization_ref") != authorization_ref
        or provenance.get("finding_ref") != repair_finding_refs(repair)[0]
        or provenance.get("source_attempt_ref") != source_ref
        or provenance.get("candidate_sha") != base_sha
        or provenance.get("packet_base_sha") != base_sha
    ):
        fail("continuation repair lease provenance is discontinuous")
    for item in disallowed:
        path, operation = item["path"], item["operation"]
        if operation != "modify" or not zone_allows(ticket.get("zone", []), path, "create"):
            fail(f"continuation repair lease expansion is outside create-to-modify provenance: {path}")
        if any(path == denied_path or path.startswith(denied_path + "/") for denied_path in denied):
            fail(f"continuation repair lease expansion conflicts with packet deny list: {path}")
    expected_expanded = [{"path": item["path"], "operations": ["modify"]} for item in disallowed]
    if provenance.get("expanded_entries") != expected_expanded or stored_zone != requested:
        fail("continuation repair lease does not match the exact authorized packet allowlist")
    expected_lineage = [
        {
            "path": item["path"],
            "attempts": validated_repair_path_lineage(p, state, ticket, source, item["path"], base_sha),
        }
        for item in disallowed
    ]
    if provenance.get("lineage") != expected_lineage:
        fail("continuation repair provenance lineage does not match the validated source candidate")


def cmd_preserve_blocked_candidate(args: argparse.Namespace) -> dict[str, Any]:
    """Preserve an owner-authorized, fully audited BLOCKED/HANDOFF write set."""
    p = paths(args.control_root, args.run_id)
    authorization = read_json(Path(args.authorization_file).expanduser().resolve(), "continuation owner authorization")
    root_schema = schema()
    validate(authorization, root_schema["$defs"]["continuation_candidate_authorization"], root_schema, "$.authorization")
    commit_receipt_path = Path(args.commit_receipt).expanduser().resolve()
    regular_non_symlink(commit_receipt_path)
    commit_receipt_raw = commit_receipt_path.read_bytes()
    commit_receipt = read_json(commit_receipt_path, "continuation candidate commit receipt")
    if (
        commit_receipt.get("status") != "PASS"
        or not GIT_SHA_RE.fullmatch(commit_receipt.get("commit_sha", ""))
        or not GIT_SHA_RE.fullmatch(commit_receipt.get("tree_sha", ""))
    ):
        fail("continuation candidate requires a PASS receipt with commit_sha and tree_sha")
    observed, _ = load_mutation_state(p, args.owner_token)
    if observed["owner"]["token"] != args.owner_token:
        fail("owner token mismatch; stale orchestrator is fenced")
    observed_attempt = attempt_by_id(observed, args.attempt_id)
    observed_ticket = next((item for item in observed.get("tickets", []) if item.get("id") == args.ticket_id), None)
    admit_event(observed, "candidate.publish")
    observed_candidate = current_candidate_record(observed, observed_ticket) if observed_ticket else None
    observed_producer = current_candidate_producer(observed, observed_ticket) if observed_ticket else None
    if observed_attempt.get("continuation_ref"):
        existing = continuation_candidate_receipt(p, observed, observed_ticket or {}, observed_attempt)
        proof_ref = observed_attempt.get("candidate_proof_ref")
        if not proof_ref:
            fail("preserved continuation candidate lacks its shared verified proof")
        proof = verify_verified_candidate_proof(p, proof_ref)
        supplied_commit_ref = f"objects/{sha256_bytes(commit_receipt_raw)}"
        if (
            authorization.get("id") == observed_attempt.get("continuation_authorization_ref")
            and commit_receipt.get("commit_sha") == observed_attempt.get("candidate_sha")
            and commit_receipt.get("tree_sha") == observed_attempt.get("candidate_tree_sha")
            and existing.get("operation_id") == args.operation_id
            and observed_candidate is not None
            and observed_candidate.get("quality") == "CONTINUATION"
            and observed_producer is not None
            and observed_producer.get("id") == args.attempt_id
            and observed_candidate.get("proof_ref") == proof_ref
            and proof.get("quality") == "CONTINUATION"
            and proof.get("operation_id") == args.operation_id
            and proof.get("commit_receipt_ref") == supplied_commit_ref
        ):
            return {"candidate": observed_attempt["candidate_sha"], "continuation_ref": observed_attempt["continuation_ref"], "idempotent": True, "revision": observed["revision"], "control": observed["lifecycle"]["control"]}
        fail("attempt already has a different preserved continuation candidate")

    def change(state: dict[str, Any]) -> None:
        admit_event(state, "candidate.publish")
        if state["lifecycle"].get("control") != "BLOCKED":
            fail("continuation preservation requires lifecycle control BLOCKED")
        attempt = attempt_by_id(state, args.attempt_id)
        ticket = next((item for item in state.get("tickets", []) if item.get("id") == args.ticket_id), None)
        if (
            ticket is None
            or ticket.get("state") != "BLOCKED"
            or ticket.get("current_attempt") != attempt.get("id")
            or attempt.get("subject_ref") != args.ticket_id
        ):
            fail("continuation preservation requires the exact current BLOCKED ticket attempt")
        if attempt.get("epoch") != state["owner"]["epoch"]:
            fail("continuation preservation requires a current-epoch worker attempt")
        if attempt.get("kind") != "worker" or attempt.get("state") != "RETURNED":
            fail("continuation preservation requires a validated RETURNED worker attempt")
        require_runtime_stopped(p, attempt, "continuation candidate qualification")
        if attempt.get("lease", {}).get("state") != "active":
            fail("continuation preservation requires the worker's active, non-quarantined lease")
        if attempt.get("candidate_sha") is not None or attempt.get("candidate_tree_sha") is not None:
            fail("continuation preservation requires an attempt with no prior candidate")
        if attempt.get("continuation_ref") or attempt.get("continuation_authorization_ref"):
            fail("continuation candidate was already preserved")

        blocker_ref = authorization["blocker_ref"]
        blocker = next((item for item in state.get("issues", []) if item.get("id") == blocker_ref), None)
        if (
            blocker is None
            or blocker.get("impact") != "blocking"
            or blocker.get("invalidated_by")
            or blocker.get("source_ref") != attempt.get("id")
            or args.ticket_id not in blocker.get("affected_refs", [])
        ):
            fail("owner authorization must bind a current blocking issue from this exact attempt and ticket")
        if authorization.get("blocker_scope") == "external":
            if not (blocker.get("type", "").startswith("external_") or blocker.get("cause") == "environment"):
                fail("external blocker authorization requires typed external/environment issue evidence")
        elif not (blocker.get("type", "").startswith("scope_") or blocker.get("type", "").startswith("out_of_scope_")):
            fail("out-of-scope authorization requires a typed scope blocker")
        evidence_refs = set(authorization.get("evidence_refs", []))
        if blocker_ref not in evidence_refs or attempt.get("return_ref") not in evidence_refs:
            fail("owner authorization must cite both the blocker and exact validated worker return")
        affected = set(authorization.get("affected_refs", []))
        if not {args.ticket_id, attempt.get("id")}.issubset(affected):
            fail("owner authorization must name the exact ticket and attempt")
        if any(item.get("id") == authorization["id"] for item in state.get("decisions", [])):
            fail("continuation authorization ID already exists")

        worker_return = stored_payload(p, attempt.get("return_ref"), "worker return")
        packet = stored_payload(p, attempt.get("packet_ref"), "worker packet")
        validate_worker_return_semantics(worker_return, packet)
        if worker_return.get("status") not in ("BLOCKED", "HANDOFF"):
            fail("continuation preservation applies only to BLOCKED/HANDOFF worker returns")
        if not worker_return.get("files"):
            fail("continuation preservation requires a non-empty worker write-set")
        validate_continuation_provenance(p, state, ticket, attempt, packet)
        if worker_return_write_set_violations(worker_return, attempt.get("lease", {})):
            fail("continuation worker return declares paths outside its lease")

        checks = {item.get("check_id"): item for item in worker_return.get("checks", [])}
        required = {
            item.get("check_id") for item in packet.get("verification", [])
            if item.get("required", True)
        }
        if not required:
            fail("continuation preservation requires at least one required ticket check")
        external_checks = set(authorization.get("external_check_ids", []))
        check_failures = {check_id for check_id, item in checks.items() if item.get("outcome") == "fail"}
        if check_failures != external_checks:
            fail("every failed check must be explicitly attributed to the authorized external/out-of-scope blocker; continuation permits no own failures")
        if not external_checks.issubset(required):
            fail("only failed required ticket checks can be attributed to the continuation blocker")
        if not required - external_checks:
            fail("continuation preservation requires at least one passing required check outside the blocker; an all-external classification cannot erase worker-owned proof failures")
        if any(checks.get(check_id, {}).get("outcome") != "pass" for check_id in required - external_checks):
            fail("all required ticket checks outside the proven blocker must PASS")
        if any(item.get("outcome") in ("not_run", "unverifiable") for item in worker_return.get("checks", [])):
            fail("continuation preservation rejects unchecked or unverifiable implementation checks")

        criterion_outcomes = {item.get("criterion_id"): item.get("outcome") for item in worker_return.get("criteria", [])}
        external_criteria = set(authorization.get("external_criterion_ids", []))
        if not external_criteria.issubset(criterion_outcomes):
            fail("owner authorization names an unknown externally blocked ticket criterion")
        if worker_return.get("status") == "BLOCKED":
            unsatisfied = {key for key, outcome in criterion_outcomes.items() if outcome != "satisfied"}
            if unsatisfied != external_criteria:
                fail("BLOCKED continuation criteria must all pass or be explicitly bound to the external/out-of-scope blocker")
        failed_external_evidence = {
            item.get("evidence_ref") for item in checks.values()
            if item.get("check_id") in external_checks and item.get("outcome") == "fail"
        }
        for criterion_id in external_criteria:
            criterion = next((item for item in worker_return.get("criteria", []) if item.get("criterion_id") == criterion_id), None)
            if criterion is None or not set(criterion.get("evidence_refs", [])) & failed_external_evidence:
                fail("external criterion classification must be evidenced by the exact authorized external failed check")
        if any(criterion_outcomes[item] == "satisfied" for item in external_criteria):
            fail("owner authorization cannot classify a satisfied ticket criterion as externally blocked")

        checkout = Path(attempt.get("checkout") or "").expanduser().resolve()
        regular_directory(checkout, "worker checkout")
        if commit_receipt.get("checkout") and Path(commit_receipt["checkout"]).expanduser().resolve() != checkout.resolve():
            fail("continuation commit receipt checkout does not match the worker's exact checkout")
        if commit_receipt.get("base_sha") != attempt.get("base_sha"):
            fail("continuation candidate base SHA does not match the worker attempt")
        if commit_receipt.get("authority_ref") != authorization.get("id"):
            fail("continuation commit receipt is not bound to the owner authorization")
        if not GIT_SHA_RE.fullmatch(attempt.get("base_sha") or ""):
            fail("continuation preservation requires an exact Git base SHA")
        try:
            head = git_output(checkout, "rev-parse", "HEAD").decode().strip()
            tree_sha = git_output(checkout, "rev-parse", "HEAD^{tree}").decode().strip()
            parents = git_output(checkout, "rev-list", "--parents", "-n", "1", head).decode().split()
        except (OSError, UnicodeError) as exc:
            fail(f"cannot verify continuation candidate Git state: {exc}")
        if head != commit_receipt["commit_sha"] or tree_sha != commit_receipt["tree_sha"]:
            fail("continuation commit receipt does not match the checkout HEAD/tree")
        if len(parents) != 2 or parents[1] != attempt.get("base_sha"):
            fail("continuation candidate must be one direct commit on the exact worker base")
        if git_output(checkout, "status", "--porcelain=v1", "-z", "--untracked-files=all"):
            fail("continuation candidate checkout must be clean after its exact candidate commit")

        operation = next((item for item in state.get("operations", []) if item.get("id") == args.operation_id), None)
        if (
            operation is None
            or operation.get("kind") != "candidate_commit"
            or operation.get("state") not in ("prepared", "applied")
            or Path(operation.get("target", "")).expanduser().resolve() != checkout.resolve()
            or operation.get("expected_before") != attempt.get("base_sha")
            or operation.get("authority_ref") != authorization.get("id")
            or operation.get("intended_after") not in (None, head)
        ):
            fail("continuation preservation requires an exact adoptable candidate_commit operation bound to this authorization, base, and checkout")
        if operation.get("state") == "applied" and operation.get("receipt_ref") != f"objects/{sha256_bytes(commit_receipt_raw)}":
            fail("applied continuation effect receipt differs from its immutable journal receipt")

        baseline = git_tree_baseline(checkout, attempt["base_sha"])
        audit = audit_write_set(checkout, baseline, worker_return.get("files", []), attempt["lease"].get("zone", []))
        if not audit.get("pass"):
            fail(f"continuation write-set audit failed: {json.dumps(audit, sort_keys=True)}")
        if not audit.get("changed_paths"):
            fail("continuation write-set audit is empty")
        if set(audit.get("changed_paths", [])) != {
            item["path"] for item in worker_return.get("files", [])
        }:
            fail("audited write-set differs from the exact validated worker return")

        commit_ref = f"objects/{object_store(p, commit_receipt_raw)}"
        continuation = {
            "run_id": state["run_id"], "ticket_id": args.ticket_id, "attempt_id": attempt["id"],
            "return_ref": attempt["return_ref"], "return_status": worker_return["status"],
            "blocker_ref": blocker_ref, "blocker_scope": authorization["blocker_scope"],
            "authorization_ref": authorization["id"], "base_sha": attempt["base_sha"],
            "candidate_sha": head, "candidate_tree_sha": tree_sha,
            "files": worker_return["files"], "lease_zone": attempt["lease"]["zone"],
            "repair_lease_provenance": attempt.get("repair_lease_provenance"),
            "external_check_ids": sorted(external_checks),
            "external_criterion_ids": sorted(external_criteria),
            "write_set_audit": audit, "audit_hash": sha256_bytes(canonical_bytes(audit)),
            "commit_receipt_ref": commit_ref, "operation_id": args.operation_id,
            "introduced_revision": state["revision"] + 1,
        }
        continuation_ref = f"objects/{object_store(p, canonical_bytes(continuation))}"
        auth_record = dict(authorization)
        auth_record.update({
            "status": "applied", "introduced_revision": str(state["revision"] + 1),
            "intent_revision": state.get("intent", {}).get("current_revision"),
            "evidence_refs": sorted(evidence_refs | {continuation_ref, commit_ref}),
            "invalidated_by": [],
        })
        state.setdefault("decisions", []).append(auth_record)
        attempt["candidate_sha"] = head
        attempt["candidate_tree_sha"] = tree_sha
        attempt["continuation_ref"] = continuation_ref
        attempt["continuation_authorization_ref"] = authorization["id"]
        proof, proof_ref = build_verified_candidate_proof(
            p, state, ticket, attempt, operation, args.operation_id, commit_receipt, commit_receipt_raw,
            quality="CONTINUATION", parent_candidate_ref=ticket.get("current_candidate"),
        )
        if proof.get("write_set_audit_hash") != sha256_bytes(canonical_bytes(audit)):
            fail("shared candidate proof write-set audit differs from continuation eligibility audit")
        if proof.get("commit_receipt_ref") != commit_ref:
            fail("shared candidate proof changed the exact continuation commit receipt reference")
        attempt["candidate_proof_ref"] = proof_ref
        publish_candidate_projection(state, ticket, attempt, quality="CONTINUATION", blocker_refs=[blocker_ref], proof_ref=proof_ref)
        if operation.get("state") == "prepared":
            transition_effect(operation, "applied")
        transition_effect(operation, "finalized")
        operation["target"] = str(checkout)
        operation["expected_before"] = attempt["base_sha"]
        operation["intended_after"] = head
        operation["receipt_ref"] = commit_ref
        operation["proof_ref"] = proof_ref
        operation["candidate_ref"] = f"candidate-{attempt['id']}"
        operation["finalized_revision"] = state["revision"] + 1
        ev_id = f"ev-continuation-{sha256_bytes(canonical_bytes(continuation))[:16]}"
        state.setdefault("evidence", []).append({
            "id": ev_id, "hash": sha256_bytes(canonical_bytes(continuation)),
            "source": "blocked_candidate_write_set_audit", "scenario": worker_return["status"],
            "outcome": "PASS", "observer": "ledger-helper", "subject": attempt["id"],
        })
        state["lifecycle"]["control"] = "BLOCKED"
        state["lifecycle"]["reason"] = state["lifecycle"].get("reason") or "blocked_continuation_candidate_preserved"
        state["lifecycle"]["next_action"] = {
            "kind": "review_or_repair_continuation_candidate",
            "subject_refs": [args.ticket_id, attempt["id"], blocker_ref],
            "preconditions": ["owner authorization recorded", "exact candidate write-set audit PASS", "blocker remains unresolved", "ticket verdict remains BLOCKED"],
            "read_refs": ["phases/execute.md", "references/ledger.md", "references/safety.md"],
        }

    result = transaction(p, args.owner_token, args.revision, change, "blocked-continuation-candidate")
    attempt = attempt_by_id(result, args.attempt_id)
    return {
        "candidate": attempt["candidate_sha"], "candidate_tree_sha": attempt["candidate_tree_sha"],
        "continuation_ref": attempt["continuation_ref"], "idempotent": False,
        "revision": result["revision"], "control": result["lifecycle"]["control"],
        "ticket_state": next(item for item in result["tickets"] if item["id"] == args.ticket_id)["state"],
    }


def cmd_prepare_effect(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    observed, _ = load_mutation_state(p, args.owner_token)
    if observed["owner"]["token"] != args.owner_token:
        fail("owner token mismatch; stale orchestrator is fenced")
    admit_event(observed, "effect.prepare")
    existing = next((item for item in observed.get("operations", []) if item.get("id") == args.operation_id), None)
    proposed = {"kind": args.kind, "target": args.target, "expected_before": args.expected_before, "intended_after": args.intended_after, "authority_ref": args.authority_ref}
    if existing:
        if all(existing.get(key) == value for key, value in proposed.items()) and existing.get("state") == "prepared":
            return {"prepared": True, "idempotent": True, "operation_id": args.operation_id, "revision": observed["revision"], "state": existing.get("state")}
        if all(existing.get(key) == value for key, value in proposed.items()):
            fail(f"operation {args.operation_id} is terminal/in-flight ({existing.get('state')}); it cannot be re-armed")
        fail("operation ID already exists with conflicting parameters")
    def change(state: dict[str, Any]) -> None:
        admit_event(state, "effect.prepare")
        safe_id(args.operation_id, "operation_id")
        if any(item.get("id") == args.operation_id for item in state.get("operations", [])):
            fail("operation ID already exists")
        if state.get("lifecycle", {}).get("control") == "BLOCKED":
            if args.kind != "candidate_commit" or not args.authority_ref:
                fail("BLOCKED effect preparation is restricted to an owner-authorized continuation candidate commit")
            continuation_attempt = next(
                (
                    attempt for attempt in state.get("attempts", [])
                    if attempt.get("kind") == "worker"
                    and attempt.get("state") == "RETURNED"
                    and attempt.get("subject_ref") in {ticket.get("id") for ticket in state.get("tickets", []) if ticket.get("state") == "BLOCKED"}
                    and attempt.get("checkout")
                    and Path(attempt["checkout"]).expanduser().resolve() == Path(args.target).expanduser().resolve()
                    and attempt.get("base_sha") == args.expected_before
                ),
                None,
            )
            blocker = next(
                (
                    issue for issue in state.get("issues", [])
                    if issue.get("impact") == "blocking"
                    and not issue.get("invalidated_by")
                    and continuation_attempt
                    and issue.get("source_ref") == continuation_attempt.get("id")
                ),
                None,
            )
            if continuation_attempt is None or blocker is None:
                repair_attempt = next((
                    attempt for attempt in state.get("attempts", [])
                    if attempt.get("kind") == "worker"
                    and attempt.get("mode") == "repair"
                    and attempt.get("state") == "RETURNED"
                    and attempt.get("repair_authorization_ref") == args.authority_ref
                    and attempt.get("checkout")
                    and Path(attempt["checkout"]).expanduser().resolve() == Path(args.target).expanduser().resolve()
                    and attempt.get("base_sha") == args.expected_before
                    and isinstance(attempt.get("repair_contract"), dict)
                ), None)
                repair_contract = repair_attempt.get("repair_contract", {}) if repair_attempt else {}
                repair_ticket = next((
                    item for item in state.get("tickets", [])
                    if repair_attempt and item.get("id") == repair_attempt.get("subject_ref")
                ), None)
                authorization = repair_authorization_for_attempt(
                    state, repair_ticket.get("id"), repair_contract, repair_attempt.get("id")
                ) if repair_ticket and repair_contract and repair_attempt else None
                if (
                    repair_attempt is None
                    or repair_ticket is None
                    or authorization is None
                    or authorization.get("id") != args.authority_ref
                ):
                    fail("BLOCKED candidate_commit must bind an exact authorized continuation or current repair worker")
        state.setdefault("operations", []).append({"id": args.operation_id, "kind": args.kind, "target": args.target, "state": "prepared", "expected_before": args.expected_before, "intended_after": args.intended_after, "authority_ref": args.authority_ref, "receipt_ref": None})
        state["lifecycle"]["next_action"] = {"kind": "apply_prepared_effect", "subject_refs": [args.operation_id], "preconditions": ["native approved effect", "same target and expected-before", "receipt or reconciliation evidence"], "read_refs": ["references/ledger.md", "references/safety.md"]}
    result = transaction(p, args.owner_token, args.revision, change, "effect-prepared")
    return {"prepared": True, "idempotent": False, "operation_id": args.operation_id, "revision": result["revision"], "state": "prepared"}


def validate_candidate_effect_receipt(operation: dict[str, Any], receipt: dict[str, Any]) -> None:
    """Require a fully bound receipt before an applied Git effect can be adopted."""
    expected = {
        "operation_id": operation.get("id"),
        "kind": operation.get("kind"),
        "target": operation.get("target"),
        "expected_before": operation.get("expected_before"),
        "base_sha": operation.get("expected_before"),
        "authority_ref": operation.get("authority_ref"),
    }
    if receipt.get("status") != "PASS" or any(receipt.get(key) != value for key, value in expected.items()):
        fail("candidate effect receipt does not bind the exact operation, target, base, authority, and PASS status")
    commit_sha = receipt.get("commit_sha")
    tree_sha = receipt.get("tree_sha")
    if not GIT_SHA_RE.fullmatch(commit_sha or "") or not GIT_SHA_RE.fullmatch(tree_sha or ""):
        fail("candidate effect receipt must include valid commit_sha and tree_sha")
    if receipt.get("intended_after") != commit_sha or operation.get("intended_after") not in (None, commit_sha):
        fail("candidate effect receipt intended_after does not match the observed commit")
    target = Path(operation.get("target", "")).expanduser().resolve()
    checkout = Path(receipt.get("checkout", "")).expanduser().resolve()
    if not receipt.get("checkout") or checkout != target:
        fail("candidate effect receipt checkout does not match its exact operation target")


def validate_effect_observation(operation: dict[str, Any], receipt: dict[str, Any], outcome: str) -> None:
    """Validate an owner-supplied fresh resolution of a previously uncertain effect."""
    expected = {
        "operation_id": operation.get("id"),
        "kind": operation.get("kind"),
        "target": operation.get("target"),
        "expected_before": operation.get("expected_before"),
        "authority_ref": operation.get("authority_ref"),
    }
    if receipt.get("status") != "PASS" or any(receipt.get(key) != value for key, value in expected.items()):
        fail("uncertain-effect resolution must be a fresh PASS receipt bound to the exact operation")
    if outcome == "abandoned":
        if receipt.get("result", receipt.get("outcome")) not in ("unchanged", "abandoned"):
            fail("abandoning an uncertain effect requires receipt result unchanged/abandoned")
        observed_state = receipt.get("observed_before", receipt.get("actual_before", receipt.get("observed_head")))
        if operation.get("expected_before") is not None and observed_state != operation.get("expected_before"):
            fail("uncertain-effect abandonment does not prove the target stayed at expected_before")
        target = Path(operation.get("target", "")).expanduser().resolve()
        if not receipt.get("checkout") or Path(receipt["checkout"]).expanduser().resolve() != target:
            fail("uncertain-effect abandonment receipt does not bind the exact checkout")
        regular_directory(target, "uncertain effect target")
        try:
            actual_head = git_output(target, "rev-parse", "HEAD").decode().strip()
            actual_tree = git_output(target, "rev-parse", "HEAD^{tree}").decode().strip()
        except (OSError, UnicodeError) as exc:
            fail(f"cannot inspect uncertain effect target: {exc}")
        if actual_head != observed_state or receipt.get("tree_sha") != actual_tree:
            fail("uncertain-effect abandonment receipt does not match the exact observed HEAD/tree")
        if git_output(target, "status", "--porcelain=v1", "-z", "--untracked-files=all"):
            fail("uncertain-effect abandonment requires a clean checkout at expected_before")


def cmd_reconcile_effect(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    requested_result = "abandoned" if args.result == "unchanged" else args.result
    receipt = None
    receipt_raw = None
    receipt_ref = None
    if args.receipt:
        receipt_path = Path(args.receipt).expanduser().resolve()
        regular_non_symlink(receipt_path)
        receipt = read_json(receipt_path, "effect receipt")
        receipt_raw = receipt_path.read_bytes()
        receipt_ref = f"objects/{sha256_bytes(receipt_raw)}"
    observed, _ = load_mutation_state(p, args.owner_token)
    if observed["owner"]["token"] != args.owner_token:
        fail("owner token mismatch; stale orchestrator is fenced")
    admit_event(observed, "effect.reconcile")
    observed_operation = next((item for item in observed.get("operations", []) if item.get("id") == args.operation_id), None)
    if observed_operation and observed_operation.get("state") == requested_result and observed_operation.get("receipt_ref") == receipt_ref:
        return {"reconciled": True, "idempotent": True, "operation_id": args.operation_id, "state": requested_result, "revision": observed["revision"]}
    def change(state: dict[str, Any]) -> None:
        admit_event(state, "effect.reconcile")
        operation = next((item for item in state.get("operations", []) if item.get("id") == args.operation_id), None)
        if operation is None:
            fail("unknown operation")
        current = operation.get("state")
        if requested_result not in EFFECT_TRANSITIONS.get(current, frozenset()):
            fail(f"effect state {current} cannot transition to {requested_result}")
        if receipt is not None:
            if requested_result == "applied" and receipt.get("commit_sha"):
                validate_candidate_effect_receipt(operation, receipt)
                target = Path(operation.get("target", "")).expanduser().resolve()
                regular_directory(target, "effect target")
                try:
                    actual_head = git_output(target, "rev-parse", "HEAD").decode().strip()
                    actual_tree = git_output(target, "rev-parse", "HEAD^{tree}").decode().strip()
                except (OSError, UnicodeError) as exc:
                    fail(f"effect reconciliation cannot inspect Git target: {exc}")
                if actual_head != receipt.get("commit_sha") or actual_tree != receipt.get("tree_sha"):
                    fail("effect receipt does not match actual Git target HEAD/tree")
                operation["intended_after"] = receipt["commit_sha"]
            elif current == "uncertain":
                validate_effect_observation(operation, receipt, requested_result)
            else:
                if receipt.get("operation_id") not in (None, args.operation_id):
                    fail("effect receipt operation mismatch")
                if receipt.get("target") not in (None, operation.get("target")):
                    fail("effect receipt target mismatch")
                if operation.get("expected_before") and receipt.get("base_sha") not in (None, operation.get("expected_before")):
                    fail("effect receipt expected-before mismatch")
                if receipt.get("status") not in (None, "PASS"):
                    fail("effect receipt status must be PASS")
            object_store(p, receipt_raw or b"")
        elif current == "uncertain" and requested_result in ("applied", "abandoned"):
            fail("resolving an uncertain effect requires fresh exact receipt evidence")
        if requested_result == "applied" and receipt is None:
            fail("applied reconciliation requires an exact effect receipt")
        if requested_result == "abandoned" and current == "uncertain" and receipt is None:
            fail("abandoning an uncertain effect requires a fresh resolution receipt")
        transition_effect(operation, requested_result)
        if receipt_ref is not None:
            operation["receipt_ref"] = receipt_ref
        if current == "uncertain":
            operation["resolution_ref"] = receipt_ref
        if requested_result == "applied":
            state["lifecycle"]["next_action"] = {"kind": "adopt_applied_effect", "subject_refs": [args.operation_id], "preconditions": ["verify the immutable effect receipt and exact target", "finalize candidate linkage without repeating Git"], "read_refs": ["phases/recover.md", "references/ledger.md"]}
        elif requested_result == "uncertain":
            state["lifecycle"]["control"] = "BLOCKED"
            state["lifecycle"]["reason"] = "uncertain_effect_requires_authority_resolution"
            state["lifecycle"]["next_action"] = {"kind": "reconcile_uncertain_effect", "subject_refs": [args.operation_id], "preconditions": ["inspect actual target", "record fresh owner resolution evidence", "do not repeat the effect"], "read_refs": ["phases/recover.md", "references/safety.md"]}
        else:
            state["lifecycle"]["next_action"] = {"kind": "effect_abandoned_requires_new_operation", "subject_refs": [args.operation_id], "preconditions": ["this operation is terminal and cannot be re-armed", "use a new operation ID only after fresh authority and expected-before checks"], "read_refs": ["references/safety.md", "references/ledger.md"]}
    result = transaction(p, args.owner_token, args.revision, change, "effect-reconciled")
    return {"reconciled": True, "idempotent": False, "operation_id": args.operation_id, "state": next(item for item in result.get("operations", []) if item.get("id") == args.operation_id)["state"], "revision": result["revision"]}


def cmd_prepare_review(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    packet_path = Path(args.packet).expanduser().resolve()
    packet = read_json(packet_path, "review packet")
    root = schema()
    validate(packet, root["$defs"]["review_packet"], root, "$.packet")
    purpose = normalize_review_purpose(packet.get("purpose"), packet_kind="review")
    identity = packet_identity(packet)
    if identity.get("run_id") not in (None, args.run_id) or identity.get("attempt_id") != args.review_attempt_id:
        fail("review packet identity does not match review attempt")
    packet_raw = packet_path.read_bytes()
    packet_hash = sha256_bytes(packet_raw)
    observed, _ = load_mutation_state(p, args.owner_token)
    if observed.get("owner", {}).get("token") != args.owner_token:
        fail("owner token mismatch; stale orchestrator is fenced")
    prior_attempt = next((item for item in observed.get("attempts", []) if item.get("id") == args.review_attempt_id), None)
    if prior_attempt is not None:
        if prior_attempt.get("packet_hash") == packet_hash and prior_attempt.get("subject_ref") == args.ticket_id and prior_attempt.get("mode") == "change":
            return {"prepared": True, "idempotent": True, "spawn_disposition": "existing_request_do_not_spawn_again", "spawn_request_id": (prior_attempt.get("runtime") or {}).get("spawn_request_id"), "attempt_id": args.review_attempt_id, "packet_hash": packet_hash, "purpose": purpose, "revision": observed["revision"]}
        fail("review attempt ID already exists with conflicting registration")
    def change(state: dict[str, Any]) -> None:
        admit_event(state, "review.dispatch")
        ticket = next((t for t in state.get("tickets", []) if t.get("id") == args.ticket_id), None)
        is_blocked_continuation = bool(ticket and ticket.get("state") == "BLOCKED" and state["lifecycle"].get("control") == "BLOCKED")
        if ticket is None or (ticket.get("state") not in ("CANDIDATE", "REVIEW") and not is_blocked_continuation):
            fail("review preparation requires a CANDIDATE/REVIEW ticket or a BLOCKED continuation candidate")
        if purpose == "critical_axis" and ticket.get("risk") != "critical":
            fail("critical-axis review requires a critical ticket")
        worker = current_candidate_producer(state, ticket)
        if worker is None or not worker.get("candidate_sha"):
            fail("review preparation requires a frozen worker candidate")
        if is_blocked_continuation:
            if continuation_candidate_receipt(p, state, ticket, worker) is None:
                fail("BLOCKED review preparation requires an audited continuation candidate")
        elif worker.get("continuation_ref"):
            fail("continuation review requires the ticket to remain BLOCKED")
        if packet.get("subject_fingerprint") != worker.get("candidate_sha"):
            fail("review packet subject is not the current candidate")
        registration_revision = identity.get("registration_revision", identity.get("source_revision", state["revision"]))
        if registration_revision != state["revision"]:
            fail("review packet registration revision is stale")
        if identity.get("subject_revision") not in (None, worker.get("attempt_created_revision"), state["revision"]):
            fail("review packet subject revision is stale")
        binding = current_intent_binding(state) if state.get("intent") else None
        packet_intent = identity.get("intent_revision")
        if binding and packet_intent and packet_intent != binding["revision"]:
            fail("review packet intent revision is stale")
        if binding and identity.get("intent_document_hash") and identity.get("intent_document_hash") != binding["document_hash"]:
            fail("review packet intent document hash is stale")
        if any(a.get("id") == args.review_attempt_id for a in state.get("attempts", [])):
            fail("review attempt ID already exists")
        object_store(p, packet_raw)
        attempt_record = {"id": args.review_attempt_id, "kind": "review", "mode": "change", "review_purpose": purpose, "subject_ref": args.ticket_id, "packet_ref": f"objects/{packet_hash}", "packet_hash": packet_hash, "epoch": state["owner"]["epoch"], "state": "PREPARED", "lease": {"id": args.lease_id, "state": "active", "zone": []}, "route_ref": None, "checkout": None, "base_sha": worker.get("candidate_sha"), "candidate_sha": worker.get("candidate_sha"), "candidate_tree_sha": worker.get("candidate_tree_sha"), "return_ref": None, "finding_refs": [], "subject_fingerprint": worker.get("candidate_sha"), "packet_registration_revision": registration_revision, "packet_source_revision": identity.get("source_revision", registration_revision), "subject_revision": identity.get("subject_revision", state["revision"]), "attempt_created_revision": state["revision"] + 1, "return_source_revision": None}
        initialize_attempt_runtime(args.run_id, attempt_record)
        if binding:
            attempt_record.update({"intent_revision": binding["revision"], "intent_document_ref": binding["document_ref"], "intent_document_hash": binding["document_hash"]})
        state.setdefault("attempts", []).append(attempt_record)
        add_usage(state.setdefault("usage", default_usage()).setdefault("counters", zero_usage()), {"packet_bytes": packet_path.stat().st_size, "attempt_registrations": 1})
        if is_blocked_continuation:
            state["lifecycle"]["control"] = "BLOCKED"
            state["lifecycle"]["next_action"] = {"kind": "await_blocked_candidate_review", "subject_refs": [args.review_attempt_id, worker["id"]], "preconditions": ["review does not change the BLOCKED ticket verdict", "reviewed candidate remains continuation-only"], "read_refs": ["contracts/reviewer.md", "phases/execute.md"]}
        else:
            ticket["state"] = "REVIEW"
            state["lifecycle"]["next_action"] = {"kind": "await_review_return", "subject_refs": [args.review_attempt_id], "preconditions": ["reviewer stopped", "integrity baseline unchanged", "strict packet/subject match"], "read_refs": ["contracts/reviewer.md", "phases/execute.md"]}
    result = transaction(p, args.owner_token, args.revision, change)
    registered = attempt_by_id(result, args.review_attempt_id)
    return {"prepared": True, "spawn_disposition": "register_only_use_spawn_request_id_once", "spawn_request_id": registered["runtime"]["spawn_request_id"], "attempt_id": args.review_attempt_id, "packet_hash": packet_hash, "purpose": purpose, "revision": result["revision"]}


def cmd_prepare_design_review(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    packet_path = Path(args.packet).expanduser().resolve()
    packet = read_json(packet_path, "design review packet")
    root = schema()
    validate(packet, root["$defs"]["review_packet"], root, "$.packet")
    identity = packet_identity(packet)
    if identity.get("run_id") not in (None, args.run_id) or identity.get("attempt_id") != args.review_attempt_id:
        fail("design review packet identity does not match review attempt")
    if args.review_kind not in ("coverage", "plan"):
        fail("design review kind must be coverage or plan")
    reviewer_identity = nonempty_string(args.reviewer_identity, "reviewer identity")
    reviewer_role = nonempty_string(args.reviewer_role, "reviewer role")
    packet_raw = packet_path.read_bytes()
    packet_hash = sha256_bytes(packet_raw)

    def change(state: dict[str, Any]) -> None:
        admit_event(state, "review.dispatch")
        if state["lifecycle"]["phase"] != "DESIGN" and not (args.review_kind == "plan" and state["lifecycle"]["phase"] == "PLAN"):
            fail("design review preparation requires DESIGN phase (or PLAN for a plan review)")
        if state["lifecycle"]["control"] in ("ACCEPTED", "FAILED", "CANCELLED"):
            fail("terminal run is immutable; start a successor run")
        publication = current_design_publication(state)
        if packet.get("subject_fingerprint") != publication.get("publication_hash"):
            fail("design review packet subject is not the current published bundle")
        packet_criteria = {review_criterion_id(item) for item in packet.get("criteria", [])}
        required_criteria = set(publication.get("criterion_refs", []))
        if required_criteria and packet_criteria != required_criteria:
            fail("design review packet criteria do not exactly match the current publication")
        if args.review_kind not in set(packet.get("axes", [])):
            fail("design review packet axes do not include its registered review kind")
        binding = current_intent_binding(state)
        if identity.get("epoch") != state["owner"]["epoch"]:
            fail("design review packet epoch does not match current owner")
        registration_revision = identity.get("registration_revision", identity.get("source_revision"))
        if registration_revision != state["revision"]:
            fail("design review packet registration revision is stale")
        if identity.get("source_revision") not in (None, registration_revision):
            fail("legacy source_revision must equal packet registration revision")
        if identity.get("subject_revision") not in (None, publication.get("published_revision")):
            fail("design review packet subject revision is stale")
        if identity.get("intent_revision") not in (None, binding["revision"]):
            fail("design review packet intent revision is stale")
        if identity.get("intent_document_ref") not in (None, binding["document_ref"]):
            fail("design review packet intent document ref is stale")
        if identity.get("intent_document_hash") not in (None, binding["document_hash"]):
            fail("design review packet intent document hash is stale")
        existing_attempt = next((item for item in state.get("attempts", []) if item.get("id") == args.review_attempt_id), None)
        if existing_attempt:
            if existing_attempt.get("packet_hash") == packet_hash and existing_attempt.get("mode") == args.review_kind and existing_attempt.get("subject_ref") == publication.get("id") and existing_attempt.get("reviewer_identity") == reviewer_identity and existing_attempt.get("reviewer_role") == reviewer_role:
                raise IdempotentResult({"prepared": True, "idempotent": True, "spawn_disposition": "existing_request_do_not_spawn_again", "spawn_request_id": (existing_attempt.get("runtime") or {}).get("spawn_request_id"), "attempt_id": args.review_attempt_id, "review_kind": args.review_kind, "packet_hash": packet_hash, "revision": state["revision"]})
            fail("review attempt ID already exists with conflicting registration")
        object_store(p, packet_raw)
        target_refs = [*publication["document_refs"], *publication["contract_refs"], *publication["ticket_refs"], *publication["route_refs"]]
        documents = {item["id"]: item for item in state.get("documents", [])}
        target_versions = [{"ref": ref, "version": documents[ref]["version"]} for ref in publication["document_refs"]]
        target_versions.extend({"ref": ref, "version": next(item for item in state.get("contracts", []) if item["id"] == ref)["version"]} for ref in publication["contract_refs"])
        target_versions.extend({"ref": ref, "version": "ledger"} for ref in [*publication["ticket_refs"], *publication["route_refs"]])
        attempt_record = {
            "id": args.review_attempt_id, "kind": "review", "mode": args.review_kind, "subject_ref": publication["id"], "packet_ref": f"objects/{packet_hash}", "packet_hash": packet_hash,
            "epoch": state["owner"]["epoch"], "state": "PREPARED", "lease": {"id": args.lease_id, "state": "active", "zone": []}, "route_ref": None,
            "checkout": None, "base_sha": None, "candidate_sha": None, "candidate_tree_sha": None, "return_ref": None, "finding_refs": [],
            "reviewer_identity": reviewer_identity, "reviewer_role": reviewer_role, "subject_fingerprint": publication["publication_hash"], "target_artifact_refs": target_refs,
            "target_artifact_versions": target_versions, "target_revision": publication["published_revision"],
            "packet_registration_revision": registration_revision, "packet_source_revision": identity.get("source_revision", registration_revision),
            "subject_revision": publication["published_revision"], "attempt_created_revision": state["revision"] + 1, "return_source_revision": None, "review_result": None,
            "intent_revision": binding["revision"], "intent_document_ref": binding["document_ref"], "intent_document_hash": binding["document_hash"],
        }
        initialize_attempt_runtime(args.run_id, attempt_record)
        state.setdefault("attempts", []).append(attempt_record)
        add_usage(state.setdefault("usage", default_usage()).setdefault("counters", zero_usage()), {"packet_bytes": packet_path.stat().st_size, "attempt_registrations": 1})
        state["lifecycle"]["next_action"] = {"kind": "await_design_review_return", "subject_refs": [args.review_attempt_id, publication["id"]], "preconditions": ["reviewer identity/role registered", "reviewer stopped", "exact bundle fingerprint and revision"], "read_refs": ["contracts/reviewer.md", "phases/design.md", "references/ledger.md"]}

    observed, _ = load_mutation_state(p, args.owner_token)
    if observed["owner"]["token"] != args.owner_token:
        fail("owner token mismatch; stale orchestrator is fenced")
    observed_attempt = next((item for item in observed.get("attempts", []) if item.get("id") == args.review_attempt_id), None)
    if observed_attempt and observed_attempt.get("packet_hash") == packet_hash and observed_attempt.get("mode") == args.review_kind and observed_attempt.get("reviewer_identity") == reviewer_identity and observed_attempt.get("reviewer_role") == reviewer_role:
        return {"prepared": True, "idempotent": True, "spawn_disposition": "existing_request_do_not_spawn_again", "spawn_request_id": (observed_attempt.get("runtime") or {}).get("spawn_request_id"), "attempt_id": args.review_attempt_id, "review_kind": args.review_kind, "packet_hash": packet_hash, "revision": observed["revision"]}
    try:
        result = transaction(p, args.owner_token, args.revision, change)
    except IdempotentResult as prior:
        return prior.result
    registered = attempt_by_id(result, args.review_attempt_id)
    return {"prepared": True, "spawn_disposition": "register_only_use_spawn_request_id_once", "spawn_request_id": registered["runtime"]["spawn_request_id"], "attempt_id": args.review_attempt_id, "review_kind": args.review_kind, "packet_hash": packet_hash, "revision": result["revision"]}


def cmd_adjudicate(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    decision = read_json(Path(args.decision_file).expanduser().resolve(), "adjudication decision")
    root = schema()
    validate(decision, root["$defs"]["decision"], root, "$.decision")
    if decision.get("type") != "reviewer_adjudication":
        fail("adjudication decision type must be reviewer_adjudication")
    if decision.get("decision") not in ("PASS", "BLOCK", "UNVERIFIABLE"):
        fail("adjudication decision must be PASS, BLOCK, or UNVERIFIABLE")
    if not decision.get("reason") or not decision.get("evidence_refs"):
        fail("adjudication requires a reason and evidence references")
    with Lock(p["lock"]):
        state, previous_raw = load_mutation_state(p, args.owner_token, args.revision)
        admit_event(state, "review.adjudicate")
        if decision["id"] in {item.get("id") for item in state.get("decisions", [])}:
            fail("decision ID already exists")
        review_ids = set(decision.get("supersedes", []))
        reviews = [item for item in state.get("reviews", []) if item.get("id") in review_ids]
        if review_ids and len(reviews) != len(review_ids):
            fail("adjudication supersedes an unknown review")
        if not reviews:
            issue_refs = set(state.get("lifecycle", {}).get("issue_refs", []))
            if not any(item.get("type") == "reviewer_disagreement" and item.get("id") in issue_refs for item in state.get("issues", [])):
                fail("adjudication must name conflicting reviews in supersedes")
        binding = current_intent_binding(state) if state.get("intent") else None
        record = dict(decision)
        record["introduced_revision"] = str(state["revision"] + 1)
        record["intent_revision"] = binding["revision"] if binding else None
        state.setdefault("decisions", []).append(record)
        for issue in state.get("issues", []):
            if issue.get("type") == "reviewer_disagreement" and (not review_ids or set(issue.get("affected_refs", [])) & review_ids):
                issue["decision_ref"] = decision["id"]
                issue["disposition"] = "resolved by adjudication" if decision["decision"] == "PASS" else "adjudicated BLOCK"
                if decision["decision"] == "PASS":
                    issue["impact"] = "advisory"
        if decision["decision"] == "PASS":
            other_blockers = [
                item for item in state.get("issues", [])
                if item.get("impact") == "blocking" and not item.get("invalidated_by")
            ]
            open_obligations = [
                item for item in finding_obligation_projection(state)["obligations"]
                if item.get("status") != "closed"
            ]
            if other_blockers or open_obligations:
                state["lifecycle"]["control"] = "BLOCKED"
                state["lifecycle"]["reason"] = "reviewer_disagreement_adjudicated_with_open_obligations"
                state["lifecycle"]["next_action"] = {"kind": "repair_or_user_decision", "subject_refs": sorted(review_ids), "preconditions": ["adjudication PASS recorded", "resolve remaining blocking issues and verification obligations"], "read_refs": ["phases/execute.md", "contracts/reviewer.md", "references/routing.md"]}
            else:
                state["lifecycle"]["control"] = "ACTIVE"
                state["lifecycle"]["reason"] = "reviewer_disagreement_adjudicated"
                state["lifecycle"]["next_action"] = {"kind": "continue_after_adjudication", "subject_refs": sorted(review_ids), "preconditions": ["re-read adjudication evidence", "candidate remains unchanged"], "read_refs": ["contracts/reviewer.md", "references/routing.md"]}
        else:
            state["lifecycle"]["control"] = "BLOCKED"
            state["lifecycle"]["reason"] = "reviewer_disagreement_adjudicated_not_pass"
            state["lifecycle"]["next_action"] = {"kind": "repair_or_user_decision", "subject_refs": sorted(review_ids), "preconditions": ["durable repair contract or new intent authority"], "read_refs": ["phases/execute.md", "phases/intent.md", "references/routing.md"]}
        state["lifecycle"]["issue_refs"] = [ref for ref in state["lifecycle"].get("issue_refs", []) if not any(item.get("id") == ref and item.get("type") == "reviewer_disagreement" and decision["decision"] == "PASS" for item in state.get("issues", []))]
        state["revision"] += 1
        state["previous_publication_hash"] = sha256_bytes(previous_raw)
        state["updated_at"] = now()
        publish(p, state, previous_raw, "adjudication")
    return {"adjudicated": True, "decision_id": decision["id"], "decision": decision["decision"], "revision": state["revision"]}


def cmd_integrate_qualification(args: argparse.Namespace) -> dict[str, Any]:
    """Integrate one exact candidate from an immutable Phase E qualification aggregate."""
    p = paths(args.control_root, args.run_id)
    with Lock(p["lock"]):
        state, previous_raw = load_mutation_state(p, args.owner_token, args.revision)
        admit_event(state, "review.integrate")
        qualification = qualification_by_id(state, args.qualification_ref)
        ticket = next((item for item in state.get("tickets", []) if item.get("id") == qualification.get("subject_ref")), None)
        if ticket is None:
            fail("review qualification is not ticket-scoped")
        candidate = current_candidate_record(state, ticket)
        worker = current_candidate_producer(state, ticket)
        if candidate is None or worker is None or candidate.get("quality") != "DONE":
            fail("qualified integration requires the explicit current DONE candidate and producer")
        require_runtime_stopped(p, worker, "qualified candidate integration")
        for review_id in qualification.get("accepted_review_refs", []):
            review = next((item for item in state.get("reviews", []) if item.get("id") == review_id), None)
            review_attempt = attempt_by_id(state, review.get("attempt_ref")) if review and review.get("attempt_ref") else None
            if review_attempt is not None:
                require_runtime_stopped(p, review_attempt, "qualified review integration")
        if qualification.get("subject_fingerprint") != candidate.get("sha"):
            fail("review qualification is stale for the current candidate")
        if qualification.get("required_purposes") != required_review_purposes(ticket, "ticket_review"):
            fail("review qualification does not encode the current ticket risk requirements")
        if qualification.get("result") != "PASS":
            fail("integration requires a complete PASS review qualification")
        if state.get("intent") and qualification.get("intent_revision") != state.get("intent", {}).get("current_revision"):
            fail("review qualification is stale for the current intent")
        if open_ticket_finding_obligations(state, ticket["id"]):
            fail("integration is blocked by unresolved ticket-scoped finding obligations")
        relevant_blockers = [
            item for item in state.get("issues", [])
            if item.get("impact") == "blocking" and not item.get("invalidated_by")
            and (ticket["id"] in item.get("affected_refs", []) or candidate["id"] in item.get("affected_refs", []))
        ]
        if relevant_blockers:
            fail("integration is blocked by unresolved applicable issues")
        if any(effect_is_unresolved(item) for item in state.get("operations", [])):
            fail("integration is blocked by an unresolved durable effect")
        if ticket.get("state") == "INTEGRATED" and candidate.get("qualification_ref") == qualification["id"]:
            if worker.get("lease", {}).get("state") != "released":
                fail("idempotent integration found an unreleased producer lease")
            return {"integrated": True, "idempotent": True, "qualification_ref": qualification["id"], "revision": state["revision"]}
        if ticket.get("state") not in ("REVIEW", "CANDIDATE"):
            fail("qualified integration requires a ticket awaiting review/integration")
        if worker.get("lease", {}).get("state") not in ("active", "released"):
            fail("qualified integration producer lease is not safely releasable")
        next_state = copy.deepcopy(state)
        next_ticket = next(item for item in next_state["tickets"] if item.get("id") == ticket["id"])
        next_candidate = next(item for item in next_state.get("candidates", []) if item.get("id") == candidate["id"])
        next_worker = attempt_by_id(next_state, worker["id"])
        next_ticket["state"] = "INTEGRATED"
        next_candidate["review_status"] = "PASS"
        next_candidate["integration_status"] = "INTEGRATED"
        next_candidate["qualification_ref"] = qualification["id"]
        next_worker["lease"]["state"] = "released"
        if next_state.get("lifecycle", {}).get("control") == "BLOCKED":
            remaining = [
                item for item in next_state.get("issues", [])
                if item.get("impact") == "blocking" and not item.get("invalidated_by")
            ]
            if not remaining:
                next_state["lifecycle"]["control"] = "ACTIVE"
                next_state["lifecycle"]["reason"] = "qualified_review_integrated"
        next_state["lifecycle"]["next_action"] = {
            "kind": "continue_after_ticket_integration", "subject_refs": [ticket["id"], qualification["id"]],
            "preconditions": ["qualification remains current", "next ticket dependencies satisfied"],
            "read_refs": ["phases/execute.md", "references/ledger.md"],
        }
        next_state["revision"] += 1
        next_state["previous_publication_hash"] = sha256_bytes(previous_raw)
        next_state["updated_at"] = now()
        validate_ledger(next_state, verify_files=False)
        publish(p, next_state, previous_raw)
    return {"integrated": True, "idempotent": False, "qualification_ref": qualification["id"], "revision": next_state["revision"]}


def cmd_integrate(args: argparse.Namespace) -> dict[str, Any]:
    if getattr(args, "qualification_ref", None):
        return cmd_integrate_qualification(args)
    p = paths(args.control_root, args.run_id)
    if not args.integrity_receipt or not args.attempt_id or not args.review_file or not args.review_id:
        fail("legacy integration requires attempt-id, review-file, integrity-receipt, and review-id")
    integrity = read_json(Path(args.integrity_receipt), "integrity receipt")
    with Lock(p["lock"]):
        state, previous_raw = load_mutation_state(p, args.owner_token, args.revision)
        attempt = attempt_by_id(state, args.attempt_id)
        require_runtime_stopped(p, attempt, "review integration")
        if attempt.get("kind") != "review" or attempt.get("mode") == "user_assisted":
            fail("integration requires a separate immutable reviewer attempt")
        linked_ticket = next((item for item in state.get("tickets", []) if item.get("id") == attempt.get("subject_ref")), None)
        linked_candidate = current_candidate_record(state, linked_ticket) if linked_ticket else None
        linked_worker = current_candidate_producer(state, linked_ticket) if linked_ticket else None
        if linked_worker is not None:
            require_runtime_stopped(p, linked_worker, "candidate integration")
        if state.get("candidate_model_version") == "1.1" and linked_ticket and (linked_candidate is None or linked_worker is None):
            fail("integration requires the explicit current candidate and its producer attempt")
        if linked_candidate and linked_candidate.get("quality") == "CONTINUATION":
            fail("continuation-only candidate cannot be integrated (quality CONTINUATION); resolve its blocker through an authorized repair and fresh review")
        if linked_worker and linked_worker.get("continuation_ref"):
            fail("continuation-only candidate cannot be integrated; resolve its blocker through an authorized repair and fresh review")
        admit_event(state, "review.integrate")
        existing_review = next((item for item in state.get("reviews", []) if item.get("id") == args.review_id), None)
        if existing_review is not None:
            ticket = next((t for t in state.get("tickets", []) if t.get("id") == attempt.get("subject_ref")), None)
            candidate = current_candidate_record(state, ticket) if ticket else None
            worker = current_candidate_producer(state, ticket) if ticket else None
            if existing_review.get("verdict") != "PASS" or existing_review.get("subject_fingerprint") != attempt.get("candidate_sha"):
                fail("existing integration review does not match this candidate")
            if (
                ticket is None or ticket.get("state") != "INTEGRATED" or worker is None
                or worker.get("candidate_sha") != attempt.get("candidate_sha")
                or (candidate and candidate.get("quality") == "CONTINUATION")
            ):
                fail("existing integration state does not match this candidate")
            if open_ticket_finding_obligations(state, ticket["id"]):
                fail("existing integration retains unresolved ticket-scoped finding obligations")
            if attempt.get("lease", {}).get("state") not in ("active", "released") or worker.get("lease", {}).get("state") not in ("active", "released"):
                fail("existing integration has a non-releasable lease state")
            if attempt.get("lease", {}).get("state") == "released" and worker.get("lease", {}).get("state") == "released":
                return {"integrated": True, "idempotent": True, "revision": state["revision"]}
            next_state = copy.deepcopy(state)
            next_attempt = attempt_by_id(next_state, args.attempt_id)
            next_worker = attempt_by_id(next_state, worker["id"])
            next_attempt["lease"]["state"] = "released"
            next_worker["lease"]["state"] = "released"
            next_state["revision"] += 1
            next_state["previous_publication_hash"] = sha256_bytes(previous_raw)
            next_state["updated_at"] = now()
            publish(p, next_state, previous_raw)
            return {"integrated": True, "idempotent": True, "reconciled": True, "revision": next_state["revision"]}
        if attempt.get("state") not in ("PREPARED", "RETURNED"):
            fail("review attempt is not active")
        require_runtime_stopped(p, attempt, "review integration")
        packet = stored_payload(p, attempt.get("packet_ref"), "review packet")
        if packet.get("purpose") is not None:
            fail("Phase E review returns must be accepted by ingest-return and integrated by qualification-ref")
        review, digest, review_raw = ingest_payload(p, state, args.attempt_id, Path(args.review_file), attempt.get("packet_hash"), "review")
        validate_return_against_attempt(p, state, attempt, review, "review")
        if review.get("verdict") != "PASS":
            fail("integration requires reviewer PASS; BLOCK/UNVERIFIABLE remains outside integration")
        if integrity.get("status") != "PASS" or integrity.get("candidate_fingerprint") not in (None, attempt.get("candidate_sha")):
            fail("independent integrity barrier did not PASS for candidate")
        if integrity.get("ledger_hash") not in (None, sha256_file(p["ledger"])):
            fail("authoritative ledger changed before review ingest")
        subject = review.get("subject_fingerprint")
        if subject != attempt.get("candidate_sha"):
            fail("review subject is not this candidate")
        if packet.get("subject_fingerprint") != attempt.get("candidate_sha"):
            fail("review packet subject is not this candidate")
        if not packet.get("mandate"):
            fail("review packet lacks an explicit mandate")
        if args.review_id in {item.get("id") for item in state.get("reviews", [])}:
            fail("review ID already exists")
        next_state = copy.deepcopy(state)
        next_attempt = attempt_by_id(next_state, args.attempt_id)
        next_attempt["return_ref"] = f"objects/{digest}"
        next_attempt["finding_refs"] = append_review_findings(next_state, review, args.attempt_id, digest, packet=packet, subject_ref=next_attempt.get("subject_ref"))
        next_attempt["lease"]["state"] = "released"
        next_attempt["state"] = "RETURNED"
        next_attempt["return_source_revision"] = packet_identity(review).get("source_revision", next_attempt.get("packet_source_revision"))
        review_id = args.review_id
        next_state.setdefault("reviews", []).append({
            "id": review_id, "mandate": packet.get("mandate", "change"),
            "subject_fingerprint": subject, "verdict": "PASS",
            "accepted": True,
            "return_ref": f"objects/{digest}", "context_refs": review.get("context_refs", []),
            "finding_refs": next_attempt["finding_refs"],
            "finding_resolution": copy.deepcopy(review.get("finding_resolution", [])),
            "intent_revision": next_state.get("intent", {}).get("current_revision"),
            "invalidated_by": [],
        })
        ticket = next((t for t in next_state.get("tickets", []) if t.get("id") == next_attempt.get("subject_ref")), None)
        if review.get("finding_resolution") and ticket is None:
            fail("finding resolution contract requires a ticket-scoped candidate review")
        finding_projection = finding_obligation_projection(next_state)
        if ticket:
            candidate = current_candidate_record(next_state, ticket)
            worker = current_candidate_producer(next_state, ticket)
            if worker is None or worker.get("candidate_sha") != next_attempt.get("candidate_sha"):
                fail("integration requires the explicit current worker candidate")
            if candidate is not None and candidate.get("quality") == "CONTINUATION":
                fail("continuation-only candidate cannot be integrated (quality CONTINUATION)")
            if worker.get("lease", {}).get("state") not in ("active", "released"):
                fail("linked worker lease is not releasable")
            worker["lease"]["state"] = "released"
            resolution_contracts = review.get("finding_resolution", [])
            initially_open_ticket_findings = {
                item.get("finding_ref") for item in finding_projection["obligations"]
                if ticket["id"] in item.get("ticket_refs", []) and item.get("status") != "closed"
            }
            seen_resolution_findings: set[str] = set()
            for resolution_index, resolution in enumerate(resolution_contracts, start=1):
                repair_ref = resolution["finding_ref"]
                candidate_ref = resolution["candidate_ref"]
                finding = next((item for item in next_state.get("findings", []) if item.get("id") == repair_ref), None)
                if (
                    candidate is None
                    or candidate_ref != candidate.get("id")
                    or finding is None
                    or ticket["id"] not in effective_finding_ticket_refs(next_state, repair_ref)
                    or repair_ref not in initially_open_ticket_findings
                    or repair_ref in seen_resolution_findings
                ):
                    fail("finding resolution must name an open finding on this ticket and the exact current candidate")
                seen_resolution_findings.add(repair_ref)
                resolution_id = f"finding-resolution-{review_id}-{resolution_index}"
                if any(item.get("id") == resolution_id for item in next_state.get("decisions", [])):
                    fail("finding resolution decision ID already exists")
                next_state.setdefault("decisions", []).append({
                    "id": resolution_id, "type": "finding_resolution",
                    "status": "accepted", "decision": "RESOLVED",
                    "reason": resolution["reason"],
                    "evidence_refs": [review_id, *resolution["evidence_refs"]],
                    "affected_refs": [repair_ref], "candidate_ref": candidate_ref,
                    "introduced_revision": str(state["revision"] + 1),
                    "intent_revision": next_state.get("intent", {}).get("current_revision"),
                })
            if resolution_contracts:
                finding_projection = finding_obligation_projection(next_state)
                resolved_refs = {
                    item.get("finding_ref") for item in finding_projection["items"]
                    if item.get("finding_ref") in seen_resolution_findings and item.get("status") == "resolved"
                }
                if resolved_refs:
                    for issue in next_state.get("issues", []):
                        if issue.get("id") in resolved_refs or issue.get("finding_ref") in resolved_refs:
                            issue["impact"] = "advisory"
                            issue["disposition"] = f"resolved by reviewed repair {args.review_id}"
                next_state["lifecycle"]["issue_refs"] = [ref for ref in next_state["lifecycle"].get("issue_refs", []) if next((item for item in next_state.get("issues", []) if item.get("id") == ref), {}).get("impact") == "blocking"]
                open_finding_refs = {
                    item.get("finding_ref") for item in finding_projection["obligations"]
                    if item.get("status") != "closed"
                }
                findings_by_id = {item.get("id"): item for item in next_state.get("findings", [])}
                reviews_by_id = {item.get("id"): item for item in next_state.get("reviews", [])}
                attempts_by_id = {item.get("id"): item for item in next_state.get("attempts", [])}
                for issue in next_state.get("issues", []):
                    if (
                        issue.get("type") != "review_verdict"
                        or issue.get("impact") != "blocking"
                        or issue.get("invalidated_by")
                        or ticket["id"] not in issue.get("affected_refs", [])
                    ):
                        continue
                    source_ref = issue.get("source_ref")
                    source_record = reviews_by_id.get(source_ref) or attempts_by_id.get(source_ref)
                    source_finding_refs = source_record.get("finding_refs", []) if source_record else []
                    canonical_refs = {ref for ref in source_finding_refs if ref in findings_by_id}
                    if (
                        not source_record
                        or not source_finding_refs
                        or canonical_refs != set(source_finding_refs)
                        or canonical_refs & open_finding_refs
                    ):
                        continue
                    issue["impact"] = "advisory"
                    issue["disposition"] = f"source review findings resolved by accepted repair review {args.review_id}"
                    issue.setdefault("invalidated_by", []).append(args.review_id)
                next_state["lifecycle"]["issue_refs"] = [
                    ref for ref in next_state.get("lifecycle", {}).get("issue_refs", [])
                    if next((item for item in next_state.get("issues", []) if item.get("id") == ref), {}).get("impact") == "blocking"
                ]
            open_obligations = [
                item for item in finding_projection["obligations"]
                if ticket["id"] in item.get("ticket_refs", []) and item.get("status") != "closed"
            ]
            if open_obligations:
                refs = sorted({
                    ref for item in open_obligations
                    for ref in ([item.get("finding_ref")] + item.get("issue_refs", []))
                    if ref
                })
                fail(f"integration is blocked by unresolved ticket-scoped finding obligations: {', '.join(refs)}")
            ticket["state"] = "INTEGRATED"
        if ticket and next_state.get("candidate_model_version") == "1.1":
            candidate = current_candidate_record(next_state, ticket)
            if candidate and candidate.get("sha") == subject:
                candidate["review_status"] = "PASS"
                candidate["integration_status"] = "INTEGRATED"
                candidate["blocker_refs"] = sorted({
                    ref for obligation in finding_projection["obligations"]
                    if ticket["id"] in obligation.get("ticket_refs", [])
                    for ref in ([obligation.get("finding_ref")] + obligation.get("issue_refs", []))
                    if ref
                })
        if next_state.get("lifecycle", {}).get("control") == "BLOCKED":
            remaining_blockers = [
                item for item in next_state.get("issues", [])
                if item.get("impact") == "blocking" and not item.get("invalidated_by")
            ]
            remaining_obligations = [
                item for item in finding_projection["obligations"]
                if item.get("status") != "closed"
            ]
            next_state["lifecycle"]["issue_refs"] = sorted(item.get("id") for item in remaining_blockers if item.get("id"))
            if not remaining_blockers and not remaining_obligations:
                next_state["lifecycle"]["control"] = "ACTIVE"
                next_state["lifecycle"]["reason"] = "reviewed_repair_integrated"
        next_state["revision"] += 1
        next_state["previous_publication_hash"] = sha256_bytes(previous_raw)
        next_state["updated_at"] = now()
        validate_ledger(next_state, verify_files=False)
        object_store(p, review_raw)
        publish(p, next_state, previous_raw)
    return {"integrated": True, "attempt_id": args.attempt_id, "review_ref": f"objects/{digest}", "revision": next_state["revision"]}


def git_output(root: Path, *command: str) -> bytes:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *command], check=True, capture_output=True
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        fail(f"write audit cannot inspect Git root: {exc}")


def git_paths(root: Path, *command: str) -> list[str]:
    return [
        item
        for item in git_output(root, *command).decode("utf-8", "surrogateescape").split("\0")
        if item
    ]


def git_tree_baseline(root: Path, base_sha: str) -> dict[str, Any]:
    """Build a complete fingerprint manifest from an exact committed Git tree."""
    raw = git_output(root, "ls-tree", "-r", "-z", "--full-tree", base_sha)
    files: list[dict[str, Any]] = []
    for token in (item for item in raw.split(b"\0") if item):
        header, separator, encoded_path = token.partition(b"\t")
        if not separator:
            fail("Git tree baseline contains a malformed entry")
        try:
            mode, object_type, object_id = header.decode("ascii").split(" ", 2)
            path = relative_path(encoded_path.decode("utf-8", "surrogateescape"), "Git tree path")
        except (UnicodeError, ValueError) as exc:
            fail(f"Git tree baseline contains an invalid entry: {exc}")
        if object_type != "blob":
            fail(f"Git tree baseline contains unsupported {object_type}: {path}")
        content = git_output(root, "cat-file", "blob", object_id)
        if mode == "120000":
            target = content.decode("utf-8", "surrogateescape")
            resolved = (root / path).parent.joinpath(target).resolve(strict=False)
            files.append({"path": path, "type": "symlink", "target": target, "target_inside_root": under(resolved, root)})
        else:
            file_mode = 0o755 if mode == "100755" else 0o644
            files.append({"path": path, "type": "file", "mode": file_mode, "sha256": sha256_bytes(content)})
    return {"base_sha": base_sha, "source": "git_tree", "files": files}


def audit_write_set(
    root: Path, baseline: dict[str, Any], declared: list[Any], zones: list[dict[str, Any]]
) -> dict[str, Any]:
    """Inspect the complete checkout and return a deterministic write-set receipt."""

    def status_paths() -> tuple[set[str], set[str]]:
        tokens = git_paths(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
        found: set[str] = set()
        renamed: set[str] = set()
        index = 0
        while index < len(tokens):
            record = tokens[index]
            value = record[3:] if len(record) >= 3 else record
            if value:
                found.add(value)
            if len(record) >= 2 and record[:2] in ("R ", " R", "RR", "C ", " C", "CC") and index + 1 < len(tokens):
                renamed.add(tokens[index + 1])
                found.add(tokens[index + 1])
                index += 1
            index += 1
        return found, renamed

    baseline_entries = baseline.get("files", baseline.get("paths", []))
    baseline_map: dict[str, dict[str, Any] | None] = {}
    for item in baseline_entries:
        if isinstance(item, dict):
            baseline_map[relative_path(item.get("path"), "baseline path")] = item
        else:
            baseline_map[relative_path(item, "baseline path")] = None
    declared_paths = {
        relative_path(item.get("path"), "declared path")
        if isinstance(item, dict)
        else relative_path(item, "declared path")
        for item in declared
    }
    declared_operations = {
        relative_path(item.get("path"), "declared path"): item.get("operation")
        for item in declared
        if isinstance(item, dict) and item.get("operation")
    }
    zone_paths = [relative_path(item.get("path"), "zone path") for item in zones]

    tracked = set(git_paths(root, "ls-files", "-z"))
    status, renamed = status_paths()
    ignored = set(git_paths(root, "ls-files", "--others", "--ignored", "--exclude-standard", "-z"))
    actual: set[str] = tracked | status | ignored

    def fingerprint(rel: str) -> dict[str, Any] | None:
        path = root / rel
        try:
            info = path.lstat()
        except FileNotFoundError:
            return None
        mode = stat.S_IMODE(info.st_mode)
        if stat.S_ISLNK(info.st_mode):
            target = os.readlink(path)
            resolved = (path.parent / target).resolve(strict=False)
            return {"path": rel, "type": "symlink", "mode": mode, "target": target, "target_inside_root": under(resolved, root)}
        if stat.S_ISREG(info.st_mode):
            return {"path": rel, "type": "file", "mode": mode, "sha256": sha256_file(path)}
        if stat.S_ISDIR(info.st_mode):
            return {"path": rel, "type": "directory", "mode": mode}
        return {"path": rel, "type": "other", "mode": mode}

    fingerprints = {rel: fingerprint(rel) for rel in actual | set(baseline_map)}
    changed: set[str] = set()
    foreign_changes: set[str] = set()
    for rel, current in fingerprints.items():
        baseline_item = baseline_map.get(rel, "__missing__")
        if baseline_item == "__missing__":
            if current is not None:
                changed.add(rel)
            continue
        if current is None:
            changed.add(rel)
            if baseline_item is not None and rel not in declared_paths:
                foreign_changes.add(rel)
            continue
        if isinstance(baseline_item, dict):
            comparable = {
                key: baseline_item.get(key)
                for key in ("type", "mode", "sha256", "target", "target_inside_root")
                if key in baseline_item
            }
            if any(current.get(key) != value for key, value in comparable.items()):
                changed.add(rel)
                if rel not in declared_paths:
                    foreign_changes.add(rel)
    # Git status is an independent source for tracked and ordinary untracked
    # effects.  The baseline remains necessary for ignored files, type/mode
    # evidence, and the exact before/after receipt, but cannot normalize away
    # a path that Git still reports as changed.
    changed.update(status)
    changed.update(renamed)
    unsafe_paths: list[dict[str, Any]] = []
    for rel, item in fingerprints.items():
        if not item:
            continue
        if item.get("type") == "symlink" and not item.get("target_inside_root"):
            unsafe_paths.append({"path": rel, "reason": "symlink target escapes audit root"})
        if item.get("type") == "other":
            unsafe_paths.append({"path": rel, "reason": "unsupported file type"})
    changed_paths = sorted(changed)
    observed_operations: dict[str, str] = {}
    for rel in changed_paths:
        baseline_item = baseline_map.get(rel, "__missing__")
        current = fingerprints.get(rel)
        if baseline_item == "__missing__" and current is not None:
            observed_operations[rel] = "create"
        elif baseline_item != "__missing__" and current is None:
            observed_operations[rel] = "delete"
        else:
            observed_operations[rel] = "modify"
    undeclared = sorted(set(changed_paths) - declared_paths)
    overdeclared = sorted(declared_paths - set(changed_paths))
    operation_mismatches = sorted(
        (
            {"path": path, "declared": declared_operations[path], "actual": observed_operations[path]}
            for path in changed_paths
            if path in declared_operations and declared_operations[path] != observed_operations[path]
        ),
        key=lambda item: (item["path"], item["declared"], item["actual"]),
    )
    try:
        root_real = root.resolve()
    except OSError as exc:
        fail(f"write audit cannot resolve root: {exc}")
    def allowed(path: str) -> bool:
        clean = path.rstrip("/")
        return any(clean == zone or clean.startswith(zone.rstrip("/") + "/") for zone in zone_paths)
    outside = sorted(path for path in changed_paths if not allowed(path))
    outside_operations = sorted(
        (
            {"path": path, "operation": observed_operations[path]}
            for path in changed_paths
            if not zone_allows(zones, path, observed_operations[path])
        ),
        key=lambda item: (item["path"], item["operation"]),
    )
    return {
        "root": str(root_real),
        "actual_paths": sorted(actual),
        "changed_paths": changed_paths,
        "observed_operations": observed_operations,
        "undeclared_paths": undeclared,
        "overdeclared_paths": overdeclared,
        "operation_mismatches": operation_mismatches,
        "outside_zone": outside,
        "outside_operations": outside_operations,
        "rename_endpoints": sorted(renamed),
        "foreign_changes": sorted(foreign_changes),
        "unsafe_paths": unsafe_paths,
        "fingerprints": fingerprints,
        "pass": not undeclared
        and not overdeclared
        and not operation_mismatches
        and not outside
        and not outside_operations
        and not foreign_changes
        and not unsafe_paths
        and not renamed,
    }


def cmd_close_blocked_attempt(args: argparse.Namespace) -> dict[str, Any]:
    """Close a no-write BLOCKED repair and restore its immediate prior candidate."""
    p = paths(args.control_root, args.run_id)
    ticket_id = safe_id(args.ticket_id, "ticket_id")
    attempt_id = safe_id(args.attempt_id, "attempt_id")
    closure_id = safe_id(f"blocked-close-{attempt_id}", "blocked closure ID")

    with Lock(p["lock"]):
        state, previous_raw = load_state(p)
        if state["owner"]["token"] != args.owner_token:
            fail("owner token mismatch; stale orchestrator is fenced")
        attempt = attempt_by_id(state, attempt_id)
        ticket = next((item for item in state.get("tickets", []) if item.get("id") == ticket_id), None)
        existing_ref = attempt.get("blocked_closure_ref")
        if existing_ref:
            receipt = stored_payload(p, existing_ref, "blocked attempt closure receipt")
            restored_ref = receipt.get("restored_attempt_ref")
            if (
                receipt.get("closure_id") != closure_id
                or receipt.get("ticket_id") != ticket_id
                or receipt.get("attempt_id") != attempt_id
                or ticket is None
                or ticket.get("current_attempt") != restored_ref
                or attempt.get("lease", {}).get("state") != "released"
                or not any(item.get("id") == closure_id and item.get("type") == "blocked_attempt_closure" for item in state.get("decisions", []))
            ):
                fail("blocked attempt closure receipt exists but ledger effects are incomplete or conflicting")
            return {
                "closed": True,
                "idempotent": True,
                "attempt_id": attempt_id,
                "restored_attempt_id": restored_ref,
                "candidate_sha": receipt.get("restored_candidate_sha"),
                "receipt_ref": existing_ref,
                "revision": state["revision"],
            }
        if state["revision"] != args.revision:
            fail(f"revision mismatch: expected {args.revision}, current {state['revision']}")
        if state["lifecycle"]["control"] != "BLOCKED":
            fail("blocked attempt closure requires lifecycle control BLOCKED")
        if ticket is None or ticket.get("state") != "BLOCKED" or ticket.get("current_attempt") != attempt_id or attempt.get("subject_ref") != ticket_id:
            fail("blocked attempt closure requires the exact current BLOCKED ticket attempt")
        if attempt.get("kind") != "worker" or attempt.get("mode") != "repair" or attempt.get("state") != "RETURNED":
            fail("blocked attempt closure applies only to a returned worker repair attempt")
        require_runtime_stopped(p, attempt, "blocked attempt closure/release")
        if attempt.get("lease", {}).get("state") != "active":
            fail("blocked attempt closure requires the attempt's active lease")
        if attempt.get("candidate_sha") is not None or attempt.get("candidate_tree_sha") is not None:
            fail("blocked attempt closure requires candidate_sha and candidate_tree_sha to be null")
        if any(effect_is_unresolved(item) for item in state.get("operations", [])):
            fail("blocked attempt closure requires all unresolved effects to be finalized or abandoned")

        returned = stored_payload(p, attempt.get("return_ref"), "blocked worker return")
        schema_root = schema()
        validate(returned, schema_root["$defs"]["worker_return"], schema_root, "$.blocked_return")
        identity = packet_identity(returned)
        if (
            returned.get("status") != "BLOCKED"
            or returned.get("files") != []
            or identity.get("run_id") != state["run_id"]
            or identity.get("ticket_id") != ticket_id
            or identity.get("attempt_id") != attempt_id
            or identity.get("packet_hash") != attempt.get("packet_hash")
            or identity.get("epoch") != attempt.get("epoch")
        ):
            fail("blocked attempt closure requires an exact validated BLOCKED return declaring no files")

        attempt_index = next(index for index, item in enumerate(state.get("attempts", [])) if item.get("id") == attempt_id)
        earlier_workers = [
            item for item in state.get("attempts", [])[:attempt_index]
            if item.get("kind") == "worker" and item.get("subject_ref") == ticket_id and item.get("candidate_sha")
        ]
        if not earlier_workers:
            fail("blocked attempt closure requires a previous validated candidate for the same ticket")
        restored = earlier_workers[-1]
        if restored.get("candidate_sha") != attempt.get("base_sha"):
            fail("the last validated same-ticket candidate does not match the blocked attempt base")
        if restored.get("state") != "RETURNED" or restored.get("lease", {}).get("state") != "released" or not restored.get("candidate_tree_sha"):
            fail("the last same-ticket candidate is not a closed validated candidate")
        restored_return = stored_payload(p, restored.get("return_ref"), "restored candidate worker return")
        validate(restored_return, schema_root["$defs"]["worker_return"], schema_root, "$.restored_return")
        restored_identity = packet_identity(restored_return)
        if (
            restored_return.get("status") != "DONE"
            or restored_identity.get("run_id") != state["run_id"]
            or restored_identity.get("ticket_id") != ticket_id
            or restored_identity.get("attempt_id") != restored.get("id")
            or restored_identity.get("packet_hash") != restored.get("packet_hash")
            or restored_identity.get("epoch") != restored.get("epoch")
        ):
            fail("the last same-ticket candidate lacks an exact validated DONE return")
        provenance = attempt.get("repair_lease_provenance")
        if isinstance(provenance, dict) and (
            provenance.get("source_attempt_ref") != restored.get("id")
            or provenance.get("candidate_sha") != restored.get("candidate_sha")
            or provenance.get("packet_base_sha") != restored.get("candidate_sha")
        ):
            fail("blocked repair provenance does not point to the last validated candidate")
        other_open = [
            item.get("id") for item in state.get("attempts", [])
            if item.get("subject_ref") == ticket_id
            and item.get("id") != attempt_id
            and item.get("lease", {}).get("state") in ("active", "quarantined")
        ]
        if other_open:
            fail(f"blocked attempt closure found other open same-ticket leases: {other_open}")

        if not isinstance(attempt.get("checkout"), str) or not attempt.get("checkout"):
            fail("blocked attempt closure requires an exact checkout path")
        checkout = safe_root(attempt["checkout"], "blocked attempt checkout")
        top_level = Path(git_output(checkout, "rev-parse", "--show-toplevel").decode().strip()).resolve()
        try:
            exact_worktree = checkout.samefile(top_level)
        except OSError:
            exact_worktree = False
        if not exact_worktree:
            fail("blocked attempt checkout is not the exact Git worktree root")
        observed_head = git_output(checkout, "rev-parse", "HEAD").decode().strip()
        if observed_head != attempt.get("base_sha") or observed_head != restored.get("candidate_sha"):
            fail("blocked attempt checkout HEAD does not match its last validated candidate base")
        observed_tree = git_output(checkout, "rev-parse", "HEAD^{tree}").decode().strip()
        if observed_tree != restored.get("candidate_tree_sha"):
            fail("blocked attempt checkout tree does not match the last validated candidate")
        baseline = git_tree_baseline(checkout, observed_head)
        audit = audit_write_set(checkout, baseline, [], [])
        if not audit.get("pass") or audit.get("changed_paths"):
            fail(f"blocked attempt checkout is not unchanged: {json.dumps(audit.get('changed_paths', []), sort_keys=True)}")

        receipt = {
            "closure_id": closure_id,
            "kind": "blocked_attempt_closure",
            "run_id": state["run_id"],
            "ticket_id": ticket_id,
            "attempt_id": attempt_id,
            "source_revision": state["revision"],
            "source_ledger_hash": sha256_bytes(previous_raw),
            "return_ref": attempt.get("return_ref"),
            "return_status": "BLOCKED",
            "declared_files": [],
            "candidate_sha": None,
            "candidate_tree_sha": None,
            "lease_before": "active",
            "lease_after": "released",
            "checkout": str(checkout),
            "observed_head": observed_head,
            "observed_tree": observed_tree,
            "write_set_audit": audit,
            "restored_attempt_ref": restored["id"],
            "restored_candidate_sha": restored["candidate_sha"],
            "restored_candidate_tree_sha": restored["candidate_tree_sha"],
            "owner_epoch": state["owner"]["epoch"],
        }
        receipt_digest = object_store(p, canonical_bytes(receipt))
        receipt_ref = f"objects/{receipt_digest}"
        attempt["lease"]["state"] = "released"
        attempt["blocked_closure_ref"] = receipt_ref
        ticket["current_attempt"] = restored["id"]
        if state.get("candidate_model_version") == "1.1":
            ticket["last_worker_attempt"] = restored["id"]
            ticket["current_worker_attempt"] = None
            restored_candidate = next((item for item in state.get("candidates", []) if item.get("producer_attempt_ref") == restored["id"]), None)
            if restored_candidate:
                ticket["current_candidate"] = restored_candidate["id"]
        state.setdefault("decisions", []).append({
            "id": closure_id,
            "type": "blocked_attempt_closure",
            "status": "closed",
            "decision": "RESTORE_LAST_VALIDATED_CANDIDATE",
            "reason": "validated BLOCKED repair returned before any file or candidate change",
            "evidence_refs": [attempt["return_ref"], receipt_ref],
            "affected_refs": [ticket_id, attempt_id, restored["id"]],
            "intent_revision": state.get("intent", {}).get("current_revision"),
            "invalidated_by": [],
        })
        evidence_id = f"ev-{receipt_digest[:16]}"
        state.setdefault("evidence", []).append({
            "id": evidence_id,
            "hash": receipt_digest,
            "source": "blocked_attempt_closure",
            "scenario": "BLOCKED_NO_WRITE",
            "outcome": "RESTORED_LAST_VALIDATED_CANDIDATE",
            "observer": "ledger-helper",
            "subject": attempt_id,
        })
        state["lifecycle"]["reason"] = "blocked_attempt_closed"
        state["lifecycle"]["next_action"] = {
            "kind": "authorize_repair",
            "subject_refs": [ticket_id, restored["id"], attempt_id],
            "preconditions": ["changed repair contract", "fresh authorization and attempt ID", "dependencies remain INTEGRATED"],
            "read_refs": ["phases/execute.md", "references/ledger.md", "references/routing.md"],
        }
        state["revision"] += 1
        state["previous_publication_hash"] = sha256_bytes(previous_raw)
        state["updated_at"] = now()
        publish(p, state, previous_raw, "blocked-attempt-closed")
        return {
            "closed": True,
            "idempotent": False,
            "attempt_id": attempt_id,
            "restored_attempt_id": restored["id"],
            "candidate_sha": restored["candidate_sha"],
            "receipt_ref": receipt_ref,
            "revision": state["revision"],
            "next_action": state["lifecycle"]["next_action"],
        }


def cmd_finalize_attempt(args: argparse.Namespace) -> dict[str, Any]:
    """Record the safe terminal disposition of a returned or stopped worker attempt."""
    p = paths(args.control_root, args.run_id)
    ticket_id = safe_id(args.ticket_id, "ticket_id")
    attempt_id = safe_id(args.attempt_id, "attempt_id")
    finalization_id = safe_id(f"attempt-finalized-{attempt_id}", "attempt finalization ID")

    def validate_replay(state: dict[str, Any], attempt: dict[str, Any], ticket: dict[str, Any] | None) -> dict[str, Any]:
        receipt_ref = attempt.get("finalization_ref")
        if not receipt_ref:
            fail("attempt has no finalization receipt")
        receipt = stored_payload(p, receipt_ref, "attempt finalization receipt")
        decision = next((item for item in state.get("decisions", []) if item.get("id") == finalization_id), None)
        expected_decision = {
            "id": finalization_id,
            "type": "attempt_finalization",
            "status": "applied",
            "decision": receipt.get("decision"),
            "evidence_refs": [receipt_ref, *([receipt.get("return_ref")] if receipt.get("return_ref") else []), *([receipt.get("termination_evidence_ref")] if receipt.get("termination_evidence_ref") else [])],
            "affected_refs": [ticket_id, attempt_id, *([receipt.get("prior_attempt_ref")] if receipt.get("prior_attempt_ref") else [])],
        }
        if (
            receipt.get("kind") != "attempt_finalization"
            or receipt.get("run_id") != state.get("run_id")
            or receipt.get("ticket_id") != ticket_id
            or receipt.get("attempt_id") != attempt_id
            or receipt.get("finalization_id") != finalization_id
            or attempt.get("subject_ref") != ticket_id
            or decision is None
            or any(decision.get(key) != value for key, value in expected_decision.items())
            or ticket is None
        ):
            fail("attempt finalization receipt or immutable decision binding is incomplete or conflicting")
        return receipt

    with Lock(p["lock"]):
        state, previous_raw = load_state(p)
        if state["owner"]["token"] != args.owner_token:
            fail("owner token mismatch; stale orchestrator is fenced")
        attempt = attempt_by_id(state, attempt_id)
        ticket = next((item for item in state.get("tickets", []) if item.get("id") == ticket_id), None)
        if attempt.get("finalization_ref"):
            receipt = validate_replay(state, attempt, ticket)
            return {
                "closed": True,
                "idempotent": True,
                "attempt_id": attempt_id,
                "restored_attempt_id": receipt.get("prior_attempt_ref"),
                "candidate_sha": receipt.get("prior_candidate_sha"),
                "disposition": receipt.get("disposition"),
                "receipt_ref": attempt["finalization_ref"],
                "revision": state["revision"],
                "next_action": state.get("lifecycle", {}).get("next_action"),
            }
        state, previous_raw = load_mutation_state(p, args.owner_token, verified=(state, previous_raw))
        admit_event(state, "attempt.reconcile")
        if state["revision"] != args.revision:
            fail(f"revision mismatch: expected {args.revision}, current {state['revision']}")
        if state["lifecycle"].get("control") in TERMINAL_CONTROLS:
            fail("terminal run is immutable; start a successor run")
        if ticket is None or ticket.get("current_attempt") != attempt_id or attempt.get("subject_ref") != ticket_id:
            fail("attempt finalization requires the exact current attempt of the same ticket")
        if attempt.get("kind") != "worker":
            fail("attempt finalization applies only to worker attempts")
        if attempt.get("candidate_sha") is not None or attempt.get("candidate_tree_sha") is not None:
            fail("attempt finalization cannot rewrite or withdraw an already-published candidate")

        return_payload: dict[str, Any] | None = None
        termination: dict[str, Any] | None = None
        declared_files: list[dict[str, Any]] = []
        evidence_known = False
        if attempt.get("state") == "RETURNED":
            if not attempt.get("return_ref"):
                fail("returned attempt finalization requires its durable worker return")
            return_payload = stored_payload(p, attempt["return_ref"], "worker return")
            schema_root = schema()
            validate(return_payload, schema_root["$defs"]["worker_return"], schema_root, "$.worker_return")
            packet = stored_payload(p, attempt.get("packet_ref"), "worker packet")
            identity = packet_identity(return_payload)
            if (
                identity.get("run_id") != state["run_id"]
                or identity.get("ticket_id") != ticket_id
                or identity.get("attempt_id") != attempt_id
                or identity.get("packet_hash") != attempt.get("packet_hash")
                or identity.get("epoch") != attempt.get("epoch")
            ):
                fail("worker return identity is not bound to the exact attempt")
            validate_worker_return_semantics(return_payload, packet)
            if return_payload.get("status") not in ("BLOCKED", "HANDOFF", "FAILED"):
                fail("attempt finalization handles only durable BLOCKED, HANDOFF, or FAILED returns")
            declared_files = return_payload.get("files", [])
            evidence_known = attempt.get("lease", {}).get("state") == "active" and runtime_stop_proven(p, attempt)
        elif attempt.get("state") in ("LOST", "INTERRUPTED"):
            termination_ref = attempt.get("termination_evidence_ref")
            if termination_ref:
                termination = stored_payload(p, termination_ref, "attempt termination evidence")
            evidence_known = bool(
                attempt.get("lease", {}).get("state") == "released"
                and runtime_stop_proven(p, attempt)
                and (
                    runtime_stop_proven(p, attempt) if isinstance(attempt.get("runtime"), dict)
                    else termination and termination.get("status") == "PASS" and termination.get("writer_stopped") is True
                )
            )
        else:
            fail("attempt finalization requires a RETURNED, LOST, or INTERRUPTED worker attempt")

        prior_candidate = current_candidate_record(state, ticket)
        prior_producer = current_candidate_producer(state, ticket)
        prior_quality: str | None = None
        prior_attempt_ref: str | None = None
        prior_candidate_sha: str | None = None
        prior_candidate_tree: str | None = None
        baseline_valid = False
        if prior_candidate is not None:
            prior_quality = prior_candidate.get("quality")
            prior_attempt_ref = prior_candidate.get("producer_attempt_ref")
            prior_candidate_sha = prior_candidate.get("sha")
            prior_candidate_tree = prior_candidate.get("tree_sha")
            baseline_valid = bool(
                prior_quality in ("DONE", "CONTINUATION")
                and prior_producer is not None
                and prior_producer.get("id") == prior_attempt_ref
                and prior_producer.get("state") == "RETURNED"
                and prior_producer.get("lease", {}).get("state") == "released"
                and prior_producer.get("candidate_sha") == prior_candidate_sha
                and prior_producer.get("candidate_tree_sha") == prior_candidate_tree
                and attempt.get("base_sha") == prior_candidate_sha
            )
            if baseline_valid and prior_quality == "DONE":
                producer_return = stored_payload(p, prior_producer.get("return_ref"), "prior DONE candidate return")
                producer_identity = packet_identity(producer_return)
                baseline_valid = bool(
                    producer_return.get("status") == "DONE"
                    and producer_identity.get("run_id") == state["run_id"]
                    and producer_identity.get("ticket_id") == ticket_id
                    and producer_identity.get("attempt_id") == prior_attempt_ref
                    and producer_identity.get("packet_hash") == prior_producer.get("packet_hash")
                    and producer_identity.get("epoch") == prior_producer.get("epoch")
                )
            elif baseline_valid and prior_quality == "CONTINUATION":
                continuation = continuation_candidate_receipt(p, state, ticket, prior_producer)
                baseline_valid = bool(
                    continuation
                    and continuation.get("candidate_sha") == prior_candidate_sha
                    and continuation.get("candidate_tree_sha") == prior_candidate_tree
                )
        else:
            baseline_sha = state.get("repository", {}).get("initial_head")
            baseline_valid = bool(baseline_sha and attempt.get("base_sha") == baseline_sha)

        checkout = None
        audit: dict[str, Any] = {
            "pass": False, "changed_paths": [], "foreign_changes": [], "error": "checkout audit unavailable",
        }
        head: str | None = None
        tree: str | None = None
        expected_tree: str | None = None
        try:
            if not isinstance(attempt.get("checkout"), str) or not attempt.get("checkout"):
                fail("attempt finalization requires an exact worker checkout")
            checkout = safe_root(attempt["checkout"], "attempt finalization checkout")
            top_level = Path(git_output(checkout, "rev-parse", "--show-toplevel").decode().strip()).resolve()
            if not checkout.samefile(top_level):
                fail("attempt finalization checkout is not the exact Git worktree root")
            head = git_output(checkout, "rev-parse", "HEAD").decode().strip()
            tree = git_output(checkout, "rev-parse", "HEAD^{tree}").decode().strip()
            expected_tree = prior_candidate_tree if prior_candidate is not None else git_output(
                checkout, "rev-parse", f"{attempt.get('base_sha')}^{{tree}}"
            ).decode().strip()
            baseline = git_tree_baseline(checkout, attempt.get("base_sha"))
            audit = audit_write_set(checkout, baseline, declared_files, attempt.get("lease", {}).get("zone", []))
        except (LedgerError, OSError) as exc:
            audit = {"pass": False, "changed_paths": [], "foreign_changes": [], "error": str(exc)}

        pending_checkout_effects = [
            item.get("id") for item in state.get("operations", [])
            if effect_is_unresolved(item)
            and checkout is not None
            and Path(item.get("target", "")).expanduser().resolve() == checkout.resolve()
        ]
        unchanged = bool(
            evidence_known
            and not declared_files
            and not pending_checkout_effects
            and baseline_valid
            and checkout is not None
            and head == attempt.get("base_sha")
            and tree == expected_tree
            and audit.get("pass") is True
            and audit.get("changed_paths") == []
        )
        if not evidence_known:
            disposition_reason = "writer stop is unknown or lease remains quarantined"
        elif pending_checkout_effects:
            disposition_reason = f"unresolved checkout effects require reconciliation or adoption: {pending_checkout_effects}"
        elif not baseline_valid:
            disposition_reason = "candidate pointer, repair base, or verified initial baseline do not match"
        elif not unchanged:
            foreign = audit.get("foreign_changes", [])
            changed = audit.get("changed_paths", [])
            disposition_reason = f"checkout contains foreign or uncertain writes (foreign={foreign}, changed={changed})"
        else:
            disposition_reason = "durable non-DONE outcome returned against an unchanged verified baseline"

        prior_open = [
            item.get("id") for item in state.get("attempts", [])
            if item.get("subject_ref") == ticket_id
            and item.get("id") != attempt_id
            and item.get("lease", {}).get("state") in ("active", "quarantined")
        ]
        if prior_open:
            unchanged = False
            disposition_reason = f"other same-ticket leases remain open: {prior_open}"

        quarantine = not unchanged
        closure_decision = "QUARANTINE_FOR_RECONCILIATION" if quarantine else (
            "RETAIN_CURRENT_CANDIDATE" if prior_candidate is not None else "RETRY_FROM_VERIFIED_BASELINE"
        )
        disposition = "quarantined" if quarantine else (
            "prior_candidate_retained" if prior_candidate is not None else "verified_baseline_retry"
        )
        lease_before = attempt.get("lease", {}).get("state")
        lease_after = "quarantined" if quarantine else "released"
        receipt = {
            "kind": "attempt_finalization",
            "finalization_id": finalization_id,
            "run_id": state["run_id"],
            "ticket_id": ticket_id,
            "attempt_id": attempt_id,
            "source_revision": state["revision"],
            "source_ledger_hash": sha256_bytes(previous_raw),
            "return_ref": attempt.get("return_ref"),
            "return_status": return_payload.get("status") if return_payload else None,
            "termination_evidence_ref": attempt.get("termination_evidence_ref"),
            "attempt_state": attempt.get("state"),
            "declared_files": declared_files,
            "prior_candidate_ref": ticket.get("current_candidate"),
            "prior_attempt_ref": prior_attempt_ref,
            "prior_candidate_quality": prior_quality,
            "prior_candidate_sha": prior_candidate_sha,
            "prior_candidate_tree_sha": prior_candidate_tree,
            "base_sha": attempt.get("base_sha"),
            "checkout": str(checkout) if checkout else attempt.get("checkout"),
            "observed_head": head,
            "observed_tree": tree,
            "write_set_audit": audit,
            "pending_checkout_effects": pending_checkout_effects,
            "baseline_valid": baseline_valid,
            "writer_stop_proven": evidence_known,
            "lease_before": lease_before,
            "lease_after": lease_after,
            "decision": closure_decision,
            "disposition": disposition,
            "reason": disposition_reason,
            "owner_epoch": state.get("owner", {}).get("epoch"),
        }
        receipt_digest = object_store(p, canonical_bytes(receipt))
        receipt_ref = f"objects/{receipt_digest}"
        attempt["lease"]["state"] = lease_after
        attempt["finalization_ref"] = receipt_ref
        decision_evidence = [receipt_ref]
        if attempt.get("return_ref"):
            decision_evidence.append(attempt["return_ref"])
        if attempt.get("termination_evidence_ref"):
            decision_evidence.append(attempt["termination_evidence_ref"])
        decision_affected = [ticket_id, attempt_id]
        if prior_attempt_ref:
            decision_affected.append(prior_attempt_ref)
        state.setdefault("decisions", []).append({
            "id": finalization_id,
            "type": "attempt_finalization",
            "status": "applied",
            "decision": closure_decision,
            "reason": disposition_reason,
            "evidence_refs": decision_evidence,
            "affected_refs": decision_affected,
            "intent_revision": state.get("intent", {}).get("current_revision"),
            "invalidated_by": [],
        })
        evidence_id = f"ev-attempt-finalized-{receipt_digest[:16]}"
        state.setdefault("evidence", []).append({
            "id": evidence_id,
            "hash": receipt_digest,
            "source": "attempt_finalization",
            "scenario": attempt.get("state"),
            "outcome": disposition,
            "observer": "ledger-helper",
            "subject": attempt_id,
        })
        retry_from_initial_baseline = bool(not quarantine and prior_candidate is None)
        resolved_retry_issue_refs: set[str] = set()
        if retry_from_initial_baseline:
            for issue in state.get("issues", []):
                if (
                    issue.get("source_ref") == attempt_id
                    and issue.get("cause") in ("implementation", "orchestration", "ownership")
                    and not issue.get("invalidated_by")
                ):
                    issue["impact"] = "advisory"
                    issue["disposition"] = f"superseded by verified baseline retry {finalization_id}"
                    issue.setdefault("invalidated_by", []).append(finalization_id)
                    resolved_retry_issue_refs.add(issue["id"])
            state["lifecycle"]["issue_refs"] = [
                ref for ref in state["lifecycle"].get("issue_refs", [])
                if ref not in resolved_retry_issue_refs
            ]
        ticket["state"] = "READY" if retry_from_initial_baseline else "BLOCKED"
        ticket["current_worker_attempt"] = None
        if state.get("candidate_model_version") == "1.1":
            # current_attempt and last_worker_attempt identify the latest worker;
            # current_candidate independently retains the explicit quality pointer.
            ticket["current_attempt"] = attempt_id
            ticket["last_worker_attempt"] = attempt_id
        state["lifecycle"]["control"] = "ACTIVE" if retry_from_initial_baseline else "BLOCKED"
        state["lifecycle"]["reason"] = "attempt_finalization_quarantined" if quarantine else (
            "attempt_finalized_prior_candidate" if prior_candidate is not None else "attempt_finalized_no_candidate"
        )
        state["lifecycle"]["next_action"] = {
            "kind": "recover_attempt" if quarantine else ("authorize_repair" if prior_candidate is not None else "retry_changed_attempt"),
            "subject_refs": [attempt_id, *([ticket_id] if not quarantine else [])],
            "preconditions": [
                "inspect exact foreign/uncertain checkout writes and reconcile quarantine" if quarantine
                else ("retain the explicit prior candidate quality" if prior_candidate is not None else "use verified baseline and a changed attempt plan or repair contract"),
                "use a fresh attempt ID",
            ],
            "read_refs": ["phases/recover.md", "phases/execute.md", "references/ledger.md"],
        }
        state["revision"] += 1
        state["previous_publication_hash"] = sha256_bytes(previous_raw)
        state["updated_at"] = now()
        publish(p, state, previous_raw, "attempt-finalized")
        return {
            "closed": True,
            "idempotent": False,
            "attempt_id": attempt_id,
            "restored_attempt_id": prior_attempt_ref,
            "candidate_sha": prior_candidate_sha,
            "disposition": disposition,
            "reason": disposition_reason,
            "receipt_ref": receipt_ref,
            "revision": state["revision"],
            "next_action": state["lifecycle"]["next_action"],
        }


def cmd_reconcile_finalized_attempt(args: argparse.Namespace) -> dict[str, Any]:
    """Release a finalized quarantine only after stop proof and baseline cleanup."""
    p = paths(args.control_root, args.run_id)
    ticket_id = safe_id(args.ticket_id, "ticket_id")
    attempt_id = safe_id(args.attempt_id, "attempt_id")
    reconciliation_id = safe_id(
        f"attempt-finalization-reconciled-{attempt_id}",
        "attempt finalization reconciliation ID",
    )
    evidence_path = Path(args.evidence).expanduser().resolve()
    evidence = read_json(evidence_path, "attempt finalization reconciliation evidence")
    evidence_raw = evidence_path.read_bytes()
    if (
        evidence.get("status") != "PASS"
        or evidence.get("writer_stopped") is not True
        or evidence.get("reconciled") is not True
        or evidence.get("disposition") != "discarded_to_verified_baseline"
    ):
        fail(
            "finalized quarantine reconciliation requires PASS writer_stopped, "
            "reconciled, and discarded_to_verified_baseline evidence"
        )

    def replay(state: dict[str, Any], attempt: dict[str, Any]) -> dict[str, Any]:
        receipt_ref = attempt.get("finalization_reconciliation_ref")
        if not receipt_ref:
            fail("attempt has no finalization reconciliation receipt")
        receipt = stored_payload(p, receipt_ref, "attempt finalization reconciliation receipt")
        decision = next(
            (item for item in state.get("decisions", []) if item.get("id") == reconciliation_id),
            None,
        )
        expected_evidence_hash = sha256_bytes(evidence_raw)
        if (
            receipt.get("kind") != "attempt_finalization_reconciliation"
            or receipt.get("reconciliation_id") != reconciliation_id
            or receipt.get("run_id") != state.get("run_id")
            or receipt.get("ticket_id") != ticket_id
            or receipt.get("attempt_id") != attempt_id
            or receipt.get("reconciliation_evidence_hash") != expected_evidence_hash
            or decision is None
            or decision.get("type") != "attempt_finalization_reconciliation"
            or decision.get("decision") != "RELEASE_VERIFIED_BASELINE"
            or decision.get("evidence_refs") != [
                receipt.get("original_finalization_ref"),
                receipt.get("reconciliation_evidence_ref"),
                receipt_ref,
            ]
            or decision.get("affected_refs") != [ticket_id, attempt_id]
        ):
            fail("attempt finalization reconciliation replay is incomplete or conflicting")
        return receipt

    with Lock(p["lock"]):
        state, previous_raw = load_state(p)
        if state.get("owner", {}).get("token") != args.owner_token:
            fail("owner token mismatch; stale orchestrator is fenced")
        attempt = attempt_by_id(state, attempt_id)
        if attempt.get("finalization_reconciliation_ref"):
            receipt = replay(state, attempt)
            return {
                "reconciled": True,
                "idempotent": True,
                "attempt_id": attempt_id,
                "disposition": receipt.get("disposition"),
                "receipt_ref": attempt["finalization_reconciliation_ref"],
                "revision": state["revision"],
                "next_action": state.get("lifecycle", {}).get("next_action"),
            }

        state, previous_raw = load_mutation_state(
            p, args.owner_token, verified=(state, previous_raw)
        )
        admit_event(state, "attempt.reconcile")
        if state["revision"] != args.revision:
            fail(f"revision mismatch: expected {args.revision}, current {state['revision']}")
        if state.get("lifecycle", {}).get("control") in TERMINAL_CONTROLS:
            fail("terminal run is immutable; start a successor run")
        ticket = next(
            (item for item in state.get("tickets", []) if item.get("id") == ticket_id),
            None,
        )
        attempt = attempt_by_id(state, attempt_id)
        if (
            ticket is None
            or ticket.get("current_attempt") != attempt_id
            or attempt.get("subject_ref") != ticket_id
        ):
            fail("reconciliation requires the exact current attempt of the same ticket")
        require_runtime_stopped(p, attempt, "finalized quarantine release/reuse")
        if attempt.get("lease", {}).get("state") != "quarantined":
            fail("reconciliation requires a finalized quarantined lease")
        finalization_ref = attempt.get("finalization_ref")
        if not finalization_ref:
            fail("reconciliation requires an immutable attempt finalization receipt")
        finalization = stored_payload(p, finalization_ref, "attempt finalization receipt")
        if (
            finalization.get("kind") != "attempt_finalization"
            or finalization.get("ticket_id") != ticket_id
            or finalization.get("attempt_id") != attempt_id
            or finalization.get("disposition") != "quarantined"
            or finalization.get("lease_after") != "quarantined"
        ):
            fail("reconciliation source is not the exact quarantined finalization")
        if not finalization.get("baseline_valid"):
            fail("quarantine cannot be released without a previously verified candidate/base binding")

        prior_candidate_ref = finalization.get("prior_candidate_ref")
        prior_candidate = current_candidate_record(state, ticket)
        if prior_candidate_ref:
            if (
                prior_candidate is None
                or prior_candidate.get("id") != prior_candidate_ref
                or prior_candidate.get("sha") != finalization.get("prior_candidate_sha")
                or prior_candidate.get("tree_sha") != finalization.get("prior_candidate_tree_sha")
            ):
                fail("current candidate changed before quarantine reconciliation")
            expected_tree = prior_candidate.get("tree_sha")
        else:
            if prior_candidate is not None or ticket.get("current_candidate") is not None:
                fail("candidate appeared before initial-baseline quarantine reconciliation")
            expected_tree = None

        checkout_value = attempt.get("checkout")
        if not isinstance(checkout_value, str) or not checkout_value:
            fail("reconciliation requires the exact worker checkout")
        checkout = safe_root(checkout_value, "attempt finalization reconciliation checkout")
        top_level = Path(git_output(checkout, "rev-parse", "--show-toplevel").decode().strip()).resolve()
        if not checkout.samefile(top_level):
            fail("reconciliation checkout is not the exact Git worktree root")
        head = git_output(checkout, "rev-parse", "HEAD").decode().strip()
        tree = git_output(checkout, "rev-parse", "HEAD^{tree}").decode().strip()
        if expected_tree is None:
            expected_tree = git_output(
                checkout, "rev-parse", f"{attempt.get('base_sha')}^{{tree}}"
            ).decode().strip()
        baseline = git_tree_baseline(checkout, attempt.get("base_sha"))
        audit = audit_write_set(checkout, baseline, [], [])
        if (
            head != attempt.get("base_sha")
            or tree != expected_tree
            or audit.get("pass") is not True
            or audit.get("changed_paths")
        ):
            fail(
                "reconciliation requires the checkout to be discarded to the exact verified baseline: "
                f"{json.dumps(audit, sort_keys=True)}"
            )
        pending_effects = [
            item.get("id") for item in state.get("operations", [])
            if effect_is_unresolved(item)
            and Path(item.get("target", "")).expanduser().resolve() == checkout.resolve()
        ]
        if pending_effects:
            fail(f"reconciliation requires all checkout effects to be resolved: {pending_effects}")
        other_open = [
            item.get("id") for item in state.get("attempts", [])
            if item.get("id") != attempt_id
            and item.get("subject_ref") == ticket_id
            and item.get("lease", {}).get("state") in ("active", "quarantined")
        ]
        if other_open:
            fail(f"reconciliation found other open same-ticket leases: {other_open}")

        evidence_digest = object_store(p, evidence_raw)
        evidence_ref = f"objects/{evidence_digest}"
        receipt = {
            "kind": "attempt_finalization_reconciliation",
            "reconciliation_id": reconciliation_id,
            "run_id": state["run_id"],
            "ticket_id": ticket_id,
            "attempt_id": attempt_id,
            "source_revision": state["revision"],
            "source_ledger_hash": sha256_bytes(previous_raw),
            "original_finalization_ref": finalization_ref,
            "reconciliation_evidence_ref": evidence_ref,
            "reconciliation_evidence_hash": evidence_digest,
            "checkout": str(checkout),
            "base_sha": attempt.get("base_sha"),
            "observed_head": head,
            "observed_tree": tree,
            "write_set_audit": audit,
            "prior_candidate_ref": prior_candidate_ref,
            "lease_before": "quarantined",
            "lease_after": "released",
            "decision": "RELEASE_VERIFIED_BASELINE",
            "disposition": (
                "prior_candidate_retained" if prior_candidate_ref else "verified_baseline_retry"
            ),
            "owner_epoch": state.get("owner", {}).get("epoch"),
        }
        receipt_digest = object_store(p, canonical_bytes(receipt))
        receipt_ref = f"objects/{receipt_digest}"
        attempt["lease"]["state"] = "released"
        attempt["finalization_reconciliation_ref"] = receipt_ref

        resolved_issue_refs: set[str] = set()
        for issue in state.get("issues", []):
            if (
                issue.get("source_ref") == attempt_id
                and issue.get("type") in ("attempt_termination", "write_set_violation")
                and not issue.get("invalidated_by")
            ):
                issue["impact"] = "advisory"
                issue["disposition"] = f"resolved by {reconciliation_id}"
                issue.setdefault("invalidated_by", []).append(reconciliation_id)
                resolved_issue_refs.add(issue["id"])
        state["lifecycle"]["issue_refs"] = [
            ref for ref in state["lifecycle"].get("issue_refs", [])
            if ref not in resolved_issue_refs
        ]
        state.setdefault("decisions", []).append({
            "id": reconciliation_id,
            "type": "attempt_finalization_reconciliation",
            "status": "applied",
            "decision": "RELEASE_VERIFIED_BASELINE",
            "reason": "writer stop and exact baseline cleanup were proven after quarantine",
            "evidence_refs": [finalization_ref, evidence_ref, receipt_ref],
            "affected_refs": [ticket_id, attempt_id],
            "intent_revision": state.get("intent", {}).get("current_revision"),
            "invalidated_by": [],
        })
        state.setdefault("evidence", []).append({
            "id": f"ev-attempt-reconciled-{receipt_digest[:16]}",
            "hash": receipt_digest,
            "source": "attempt_finalization_reconciliation",
            "scenario": attempt.get("state"),
            "outcome": receipt["disposition"],
            "observer": "ledger-helper",
            "subject": attempt_id,
        })
        ticket["current_worker_attempt"] = None
        if prior_candidate_ref:
            ticket["state"] = "BLOCKED"
            state["lifecycle"]["control"] = "BLOCKED"
            state["lifecycle"]["reason"] = "attempt_finalized_prior_candidate"
            next_action = {
                "kind": "authorize_repair",
                "subject_refs": [ticket_id, attempt_id],
                "preconditions": ["retain the explicit prior candidate quality", "use a fresh attempt ID"],
                "read_refs": ["phases/execute.md", "references/ledger.md"],
            }
        else:
            ticket["state"] = "READY"
            state["lifecycle"]["control"] = "ACTIVE"
            state["lifecycle"]["reason"] = "attempt_finalized_no_candidate"
            next_action = {
                "kind": "retry_changed_attempt",
                "subject_refs": [ticket_id, attempt_id],
                "preconditions": ["use the verified baseline", "change the attempt plan", "use a fresh attempt ID"],
                "read_refs": ["phases/execute.md", "references/ledger.md"],
            }
        state["lifecycle"]["next_action"] = next_action
        state["revision"] += 1
        state["previous_publication_hash"] = sha256_bytes(previous_raw)
        state["updated_at"] = now()
        publish(p, state, previous_raw, "attempt-finalization-reconciled")
        return {
            "reconciled": True,
            "idempotent": False,
            "attempt_id": attempt_id,
            "disposition": receipt["disposition"],
            "receipt_ref": receipt_ref,
            "revision": state["revision"],
            "next_action": state["lifecycle"]["next_action"],
        }


def cmd_reconcile_quarantined_attempt(args: argparse.Namespace) -> dict[str, Any]:
    """Reconcile one legacy create-only repair lease without weakening quarantine."""
    p = paths(args.control_root, args.run_id)
    reconciliation_id = safe_id(args.reconciliation_id, "reconciliation_id")
    ticket_id = safe_id(args.ticket_id, "ticket_id")
    attempt_id = safe_id(args.attempt_id, "attempt_id")
    prior_attempt_id = safe_id(args.prior_attempt_id, "prior_attempt_id")
    finding_ref = safe_id(args.finding_ref, "finding_ref")
    actor = nonempty_string(args.actor, "reconciliation actor")
    if not GIT_SHA_RE.fullmatch(args.candidate_sha or "") or not GIT_SHA_RE.fullmatch(args.base_sha or ""):
        fail("reconciliation requires exact candidate and base Git SHAs")
    baseline: dict[str, Any] | None = None
    baseline_raw: bytes | None = None
    baseline_hash: str | None = None
    if args.baseline:
        baseline_path = Path(args.baseline).expanduser().resolve()
        regular_non_symlink(baseline_path)
        baseline_raw = baseline_path.read_bytes()
        try:
            baseline = json.loads(baseline_raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            fail(f"invalid reconciliation baseline {baseline_path}: {exc}")
        if not isinstance(baseline, dict):
            fail("reconciliation baseline must be an object")
        baseline_hash = sha256_bytes(baseline_raw)
    base_binding = {
        "reconciliation_id": reconciliation_id,
        "actor": actor,
        "ticket_id": ticket_id,
        "attempt_id": attempt_id,
        "prior_attempt_id": prior_attempt_id,
        "finding_ref": finding_ref,
        "candidate_sha": args.candidate_sha,
        "base_sha": args.base_sha,
    }

    with Lock(p["lock"]):
        state, previous_raw = load_state(p)
        if state["owner"]["token"] != args.owner_token:
            fail("owner token mismatch; stale orchestrator is fenced")
        attempt = attempt_by_id(state, attempt_id)
        existing_ref = attempt.get("quarantine_reconciliation_ref")
        if existing_ref:
            existing = stored_payload(p, existing_ref, "quarantine reconciliation receipt")
            observed_binding = {key: existing.get(key) for key in base_binding}
            prior = next((item for item in state.get("attempts", []) if item.get("id") == prior_attempt_id), None)
            decision = next((item for item in state.get("decisions", []) if item.get("id") == reconciliation_id), None)
            baseline_matches = (
                existing.get("baseline_sha256") == baseline_hash
                if baseline_hash is not None
                else existing.get("baseline_source") == "git_base"
            )
            expected_decision = {
                "id": reconciliation_id,
                "type": "quarantine_reconciliation",
                "status": "applied",
                "decision": "RECONCILE",
                "evidence_refs": [finding_ref, existing.get("baseline_ref"), existing_ref],
                "affected_refs": [ticket_id, attempt_id, prior_attempt_id, finding_ref],
            }
            if (
                observed_binding != base_binding
                or not baseline_matches
                or existing.get("kind") != "quarantined_attempt_reconciliation"
                or attempt.get("quarantine_reconciliation_ref") != existing_ref
                or prior is None
                or decision is None
                or any(decision.get(key) != value for key, value in expected_decision.items())
            ):
                fail("quarantined attempt was already reconciled with different evidence")
            return {
                "reconciled": True,
                "idempotent": True,
                "reconciliation_id": existing.get("reconciliation_id"),
                "attempt_id": attempt_id,
                "receipt_ref": existing_ref,
                "revision": state["revision"],
            }
        state, previous_raw = load_mutation_state(p, args.owner_token, verified=(state, previous_raw))
        admit_event(state, "attempt.reconcile")
        if state["revision"] != args.revision:
            fail(f"revision mismatch: expected {args.revision}, current {state['revision']}")
        if state["lifecycle"]["control"] in ("ACCEPTED", "FAILED", "CANCELLED"):
            fail("terminal run is immutable; start a successor run")
        if any(item.get("id") == reconciliation_id for item in state.get("decisions", [])):
            fail("reconciliation ID already exists")
        ticket = next((item for item in state.get("tickets", []) if item.get("id") == ticket_id), None)
        if ticket is None or attempt.get("subject_ref") != ticket_id or ticket.get("current_attempt") != attempt_id:
            fail("reconciliation requires the exact current attempt of the same ticket")
        require_runtime_stopped(p, attempt, "quarantined repair lease release/reuse")
        if attempt.get("kind") != "worker" or attempt.get("mode") != "repair" or attempt.get("state") != "RETURNED":
            fail("reconciliation requires a returned worker repair attempt")
        if attempt.get("lease", {}).get("state") != "quarantined":
            fail("reconciliation applies only to an existing quarantined lease")
        if attempt.get("candidate_sha") is not None:
            fail("reconciliation must precede candidate publication")

        packet = stored_payload(p, attempt.get("packet_ref"), "quarantined worker packet")
        schema_root = schema()
        validate(packet, schema_root["$defs"]["worker_packet"], schema_root, "$.packet")
        packet_identity_value = packet_identity(packet)
        repair = packet.get("repair")
        if (
            packet.get("kind") != "worker"
            or packet.get("mode") != "repair"
            or packet_identity_value.get("run_id") != args.run_id
            or packet_identity_value.get("ticket_id") != ticket_id
            or packet_identity_value.get("attempt_id") != attempt_id
            or not isinstance(repair, dict)
        ):
            fail("quarantined packet identity/mode does not match reconciliation")
        if attempt.get("repair_contract") != repair:
            fail("quarantined attempt repair contract does not match its packet")
        if repair.get("finding_ref") != finding_ref:
            fail("reconciliation finding does not match the repair contract")

        authorization = active_repair_authorization(state, ticket_id, finding_ref)
        if authorization is None or attempt.get("repair_authorization_ref") not in (None, authorization.get("id")):
            fail("reconciliation requires the exact accepted repair authorization")
        contract_refs = [
            ref for ref in authorization.get("evidence_refs", [])
            if isinstance(ref, str) and ref.startswith("objects/")
        ]
        if contract_refs:
            if len(contract_refs) != 1 or stored_payload(p, contract_refs[0], "authorized repair contract") != repair:
                fail("reconciliation repair contract is not hash-bound to its authorization")
        elif finding_ref not in authorization.get("evidence_refs", []) or authorization.get("reason") != repair.get("hypothesis"):
            fail("legacy repair authorization is not bound to the exact finding and hypothesis")
        finding_record = next((item for item in state.get("findings", []) if item.get("id") == finding_ref), None)
        issue_record = next((item for item in state.get("issues", []) if item.get("id") == finding_ref), None)
        if issue_record and issue_record.get("finding_ref"):
            finding_record = next((item for item in state.get("findings", []) if item.get("id") == issue_record.get("finding_ref")), finding_record)
        legacy_review = next(
            (item for item in state.get("attempts", []) if finding_record and item.get("id") == finding_record.get("source_ref")),
            None,
        )
        legacy_candidate_binding = bool(
            finding_record
            and finding_record.get("impact") == "blocking"
            and not finding_record.get("invalidated_by")
            and legacy_review
            and legacy_review.get("kind") == "review"
            and legacy_review.get("subject_ref") == ticket_id
            and legacy_review.get("state") == "RETURNED"
            and legacy_review.get("candidate_sha") == args.candidate_sha
            and finding_ref in legacy_review.get("finding_refs", [])
        )
        if not finding_matches_candidate(state, finding_ref, ticket_id, args.candidate_sha) and not legacy_candidate_binding:
            fail("reconciliation requires a current blocking finding bound to the exact candidate")

        repair_source_ref = repair.get("source_attempt_ref")
        if repair_source_ref != prior_attempt_id:
            source = attempt_by_id(state, repair_source_ref)
            if (
                finding_record is None
                or finding_record.get("source_ref") != repair_source_ref
                or source.get("kind") != "review"
                or source.get("subject_ref") != ticket_id
                or source.get("state") != "RETURNED"
                or source.get("candidate_sha") != args.candidate_sha
                or finding_ref not in source.get("finding_refs", [])
            ):
                fail("legacy repair source is not the exact candidate-bound finding review")

        prior = attempt_by_id(state, prior_attempt_id)
        if (
            prior.get("kind") != "worker"
            or prior.get("subject_ref") != ticket_id
            or prior.get("state") != "RETURNED"
            or prior.get("candidate_sha") != args.candidate_sha
            or prior.get("lease", {}).get("state") == "quarantined"
        ):
            fail("reconciliation prior candidate provenance is missing, foreign, or quarantined")
        if attempt.get("base_sha") != args.base_sha or args.base_sha != args.candidate_sha:
            fail("reconciliation base SHA is stale or does not equal the prior candidate")
        if packet.get("workspace", {}).get("expected_base") != args.base_sha:
            fail("reconciliation packet base SHA does not match the exact base")
        if baseline is not None and baseline.get("base_sha") not in (None, args.base_sha):
            fail("reconciliation baseline is bound to a different base SHA")

        prior_return = stored_payload(p, prior.get("return_ref"), "prior worker return")
        current_return = stored_payload(p, attempt.get("return_ref"), "quarantined worker return")
        for returned, returned_attempt, label in (
            (prior_return, prior, "prior"),
            (current_return, attempt, "quarantined"),
        ):
            validate(returned, schema_root["$defs"]["worker_return"], schema_root, f"$.{label}_return")
            validate_standalone_contract(returned, "worker_return")
            identity = packet_identity(returned)
            if (
                identity.get("run_id") != args.run_id
                or identity.get("ticket_id") not in (None, ticket_id)
                or identity.get("attempt_id") != returned_attempt.get("id")
                or identity.get("packet_hash") != returned_attempt.get("packet_hash")
                or identity.get("epoch") != returned_attempt.get("epoch")
            ):
                fail(f"reconciliation {label} worker return identity is not exact")
        validate_worker_return_semantics(current_return, packet)
        if prior_return.get("status") != "DONE" or current_return.get("status") != "DONE":
            fail("reconciliation requires confirmed prior and current DONE worker returns")
        created_paths = {
            relative_path(item.get("path"), "prior created path")
            for item in prior_return.get("files", [])
            if item.get("operation") == "create"
        }
        legacy_violations = worker_return_write_set_violations(current_return, attempt.get("lease", {}))
        if not legacy_violations:
            fail("quarantined attempt has no legacy create-only lease violation to reconcile")
        requested = packet_write_zone(packet)
        ticket_zone = ticket.get("zone", [])
        denied = [
            relative_path(item, "packet write deny path").rstrip("/")
            for item in packet.get("write", {}).get("deny", [])
        ]
        expanded: list[dict[str, Any]] = []
        lineage: list[dict[str, Any]] = []
        requested_exceptions = [
            {"path": entry["path"], "operation": operation}
            for entry in requested
            for operation in entry["operations"]
            if not zone_allows(ticket_zone, entry["path"], operation)
        ]
        for violation in requested_exceptions:
            path, operation = violation["path"], violation["operation"]
            if (
                operation != "modify"
                or path not in created_paths
                or not zone_allows(ticket_zone, path, "create")
                or not zone_allows(prior.get("lease", {}).get("zone", []), path, "create")
                or not zone_allows(requested, path, "modify")
            ):
                fail(f"quarantine is not an exact same-ticket create-to-modify case: {path} ({operation})")
            if any(path == item or path.startswith(item + "/") for item in denied):
                fail(f"reconciliation path conflicts with packet deny list: {path}")
            expanded.append({"path": path, "operations": ["modify"]})
            lineage.append({
                "path": path,
                "attempts": validated_repair_path_lineage(
                    p, state, ticket, prior, path, args.candidate_sha
                ),
            })
        legacy_pairs = {(item["path"], item["operation"]) for item in legacy_violations}
        exception_pairs = {(item["path"], item["operation"]) for item in requested_exceptions}
        if not legacy_pairs.issubset(exception_pairs):
            fail("quarantined return contains violations outside the proven repair expansion")

        quarantine_issues = [
            item for item in state.get("issues", [])
            if item.get("source_ref") == attempt_id
            and item.get("impact") == "blocking"
            and not item.get("invalidated_by")
        ]
        if not quarantine_issues or any(item.get("type") != "write_set_violation" for item in quarantine_issues):
            fail("reconciliation refuses quarantine with missing or non-write-set blocking causes")

        checkout = safe_root(attempt.get("checkout") or "", "reconciliation checkout")
        regular_directory(checkout, "reconciliation checkout")
        packet_checkout = safe_root(packet.get("workspace", {}).get("root") or "", "packet checkout")
        if checkout != packet_checkout:
            fail("reconciliation checkout does not match the quarantined packet")
        git_root = Path(git_output(checkout, "rev-parse", "--show-toplevel").decode().strip()).resolve()
        if git_root != checkout:
            fail("reconciliation checkout is not the exact Git worktree root")
        observed_head = git_output(checkout, "rev-parse", "HEAD").decode().strip()
        if observed_head != args.base_sha:
            fail("reconciliation checkout HEAD is stale relative to the exact base SHA")
        baseline_source = "supplied"
        if baseline is None:
            baseline = git_tree_baseline(checkout, args.base_sha)
            baseline_raw = canonical_bytes(baseline)
            baseline_hash = sha256_bytes(baseline_raw)
            baseline_source = "git_base"
        assert baseline_raw is not None and baseline_hash is not None
        audit = audit_write_set(checkout, baseline, current_return.get("files", []), requested)
        if not audit.get("pass"):
            fail(f"reconciliation write-set audit failed: {json.dumps(audit, sort_keys=True)}")

        baseline_ref = f"objects/{object_store(p, baseline_raw)}"
        repair_contract_ref = f"objects/{object_store(p, canonical_bytes(repair))}"
        requested_binding = {**base_binding, "baseline_sha256": baseline_hash}
        provenance = {
            "authorization_ref": authorization["id"],
            "finding_ref": finding_ref,
            "source_attempt_ref": prior_attempt_id,
            "candidate_sha": args.candidate_sha,
            "packet_base_sha": args.base_sha,
            "expanded_entries": sorted(expanded, key=lambda item: item["path"]),
            "lineage": sorted(lineage, key=lambda item: item["path"]),
        }
        receipt = {
            **requested_binding,
            "kind": "quarantined_attempt_reconciliation",
            "recorded_at": now(),
            "authorization_ref": authorization["id"],
            "packet_ref": attempt.get("packet_ref"),
            "return_ref": attempt.get("return_ref"),
            "prior_return_ref": prior.get("return_ref"),
            "baseline_ref": baseline_ref,
            "baseline_source": baseline_source,
            "repair_contract_ref": repair_contract_ref,
            "legacy_lease": copy.deepcopy(attempt.get("lease")),
            "effective_lease_zone": requested,
            "repair_lease_provenance": provenance,
            "write_set_audit": audit,
            "quarantine_issue_refs": [item["id"] for item in quarantine_issues],
        }
        receipt_digest = object_store(p, canonical_bytes(receipt))
        receipt_ref = f"objects/{receipt_digest}"

        attempt["lease"]["state"] = "active"
        attempt["lease"]["zone"] = requested
        attempt["repair_authorization_ref"] = authorization["id"]
        attempt["repair_lease_provenance"] = provenance
        attempt["quarantine_reconciliation_ref"] = receipt_ref
        for issue in quarantine_issues:
            issue["impact"] = "advisory"
            issue["disposition"] = f"reconciled by {reconciliation_id}"
            issue["decision_ref"] = reconciliation_id
            issue.setdefault("invalidated_by", []).append(reconciliation_id)
        state.setdefault("decisions", []).append({
            "id": reconciliation_id,
            "type": "quarantine_reconciliation",
            "status": "applied",
            "decision": "RECONCILE",
            "reason": "legacy create-only lease proven as exact same-ticket create-to-modify repair",
            "evidence_refs": [finding_ref, baseline_ref, receipt_ref],
            "affected_refs": [ticket_id, attempt_id, prior_attempt_id, finding_ref],
            "intent_revision": state.get("intent", {}).get("current_revision"),
            "invalidated_by": [],
        })
        evidence_id = f"ev-{receipt_digest[:16]}"
        state.setdefault("evidence", []).append({
            "id": evidence_id,
            "hash": receipt_digest,
            "source": "quarantine_reconciliation",
            "scenario": "legacy_create_to_modify",
            "outcome": "PASS",
            "observer": actor,
            "subject": attempt_id,
        })
        ticket["state"] = "RUNNING"
        state["lifecycle"]["issue_refs"] = [
            ref for ref in state["lifecycle"].get("issue_refs", [])
            if ref not in {item["id"] for item in quarantine_issues}
        ]
        state["lifecycle"]["control"] = "ACTIVE"
        state["lifecycle"]["reason"] = "quarantined_attempt_reconciled"
        state["lifecycle"]["next_action"] = {
            "kind": "prepare_candidate_effect",
            "subject_refs": [attempt_id, reconciliation_id],
            "preconditions": ["reconciliation receipt remains current", "candidate base SHA unchanged"],
            "read_refs": ["phases/execute.md", "references/ledger.md"],
        }
        usage = state.setdefault("usage", default_usage())
        usage.setdefault("counters", zero_usage())
        usage.setdefault("trace", [])
        usage.setdefault("shared_setup", zero_usage())
        usage.setdefault("gate_costs", {f"G{i}": zero_usage() for i in range(7)})
        delta = {field: 0 for field in USAGE_FIELDS}
        delta["helper_calls"] = 1
        delta["internal_publications"] = 1
        add_usage(usage["counters"], delta)
        usage["trace"].append({
            "id": f"trace-{state['revision'] + 1}-helper",
            "kind": "helper_publication",
            "actor": "ledger-helper",
            "subject_ref": "prepare_candidate_effect",
            "delta": delta,
            "evidence_ref": receipt_ref,
            "recorded_at": now(),
        })
        state["revision"] += 1
        state["previous_publication_hash"] = sha256_bytes(previous_raw)
        state["updated_at"] = now()
        publish(p, state, previous_raw, "quarantine-reconciled")
        return {
            "reconciled": True,
            "idempotent": False,
            "reconciliation_id": reconciliation_id,
            "attempt_id": attempt_id,
            "receipt_ref": receipt_ref,
            "changed_paths": audit["changed_paths"],
            "revision": state["revision"],
        }


def cmd_audit(args: argparse.Namespace) -> dict[str, Any]:
    root = safe_root(args.root, "audit root")
    regular_directory(root, "audit root")
    baseline = read_json(Path(args.baseline), "baseline manifest")
    declared = read_json(Path(args.declared), "declared write set")
    zones = read_json(Path(args.zone), "lease zone")
    if not isinstance(declared, list) or not isinstance(zones, list):
        fail("declared write set and lease zone must be arrays")
    return audit_write_set(root, baseline, declared, zones)


def check_integrity(baseline: dict[str, Any], state: dict[str, Any], current_raw: bytes, expected_subject: str | None = None) -> None:
    if baseline.get("status") != "PASS":
        fail("integrity barrier is not PASS")
    if not baseline.get("ledger_hash"):
        fail("integrity barrier lacks the frozen ledger hash")
    if baseline["ledger_hash"] != sha256_bytes(current_raw):
        fail("authoritative ledger changed during review")
    if expected_subject and baseline.get("candidate_fingerprint") != expected_subject:
        fail("integrity candidate fingerprint mismatch")
    if baseline.get("candidate_sha") and not GIT_SHA_RE.fullmatch(baseline["candidate_sha"]):
        fail("invalid baseline candidate SHA")


def validate_manual_receipt(receipt: dict[str, Any], label: str) -> None:
    if receipt.get("status") != "PASS":
        fail(f"{label} is not PASS")
    if not receipt.get("receipt_id"):
        fail(f"{label} lacks receipt_id")
    if not receipt.get("inventory_hashes") and label == "environment receipt":
        fail("environment receipt lacks exported input inventory hashes")
    if label == "environment receipt" and not receipt.get("boundary_probes"):
        fail("environment receipt lacks nonsecret boundary probes")
    if label == "environment receipt" and receipt.get("authoritative_absent") is not True:
        fail("environment receipt does not attest scoped authoritative absence")
    if label == "environment receipt" and not isinstance(receipt.get("topology"), dict):
        fail("environment receipt lacks observable topology")
    if label == "context receipt" and receipt.get("grade") != "MANUAL_ATTESTED_CLEAN":
        fail("manual context receipt must be MANUAL_ATTESTED_CLEAN")
    if label == "context receipt" and receipt.get("clean_input") is not True:
        fail("context receipt lacks clean-input attestation")
    if label == "context receipt" and receipt.get("contamination_absent") is not True:
        fail("context receipt lacks contamination attestation")


def verify_manual_inventory(receipt: dict[str, Any], handoff: dict[str, Any]) -> None:
    bundle = Path(handoff.get("bundle_root", ""))
    regular_directory(bundle, "handoff bundle")
    manifest = read_json(bundle / "manifest.json", "handoff manifest")
    manifest_files = {item.get("path"): item.get("sha256") for item in manifest.get("files", [])}
    expected_manifest = handoff.get("manifest_ref", "").removeprefix("sha256:")
    manifest_path = bundle / "manifest.json"
    if expected_manifest and sha256_file(manifest_path) != expected_manifest:
        fail("handoff manifest has drifted")
    for item in receipt.get("inventory_hashes", []):
        rel = relative_path(item.get("path"), "receipt inventory path")
        expected = item.get("sha256")
        if rel.startswith("g5-bundle/"):
            actual_path = bundle / rel.removeprefix("g5-bundle/")
            regular_non_symlink(actual_path)
            if sha256_file(actual_path) != expected:
                fail(f"environment inventory hash mismatch: {rel}")
        elif rel.startswith("candidate-export/"):
            export_rel = rel.removeprefix("candidate-export/")
            if manifest_files.get(export_rel) != expected:
                fail(f"candidate export inventory does not match manifest: {rel}")
        else:
            fail(f"environment inventory path is outside prepared bundle: {rel}")


def verify_manual_inventory_exact(receipt: dict[str, Any], handoff: dict[str, Any]) -> None:
    """Require complete candidate export and prepared bundle coverage for Phase E."""
    bundle = Path(handoff.get("bundle_root", ""))
    regular_directory(bundle, "handoff bundle")
    manifest = read_json(bundle / "manifest.json", "handoff manifest")
    expected = {
        f"candidate-export/{item['path']}": item["sha256"]
        for item in manifest.get("files", [])
    }
    for name in ("packet.json", "projection.json", "manifest.json", "operator-checklist.md"):
        path = bundle / name
        regular_non_symlink(path)
        expected[f"g5-bundle/{name}"] = sha256_file(path)
    actual: dict[str, str] = {}
    for item in receipt.get("inventory_hashes", []):
        rel = relative_path(item.get("path"), "receipt inventory path")
        if rel in actual:
            fail(f"environment inventory contains a duplicate path: {rel}")
        actual[rel] = item.get("sha256")
    if actual != expected:
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        changed = sorted(path for path in set(actual) & set(expected) if actual[path] != expected[path])
        fail(f"environment inventory is not the exact prepared export: missing={missing}, extra={extra}, changed={changed}")


def cmd_prepare_handoff(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    packet_path = Path(args.packet).expanduser().resolve()
    projection_path = Path(args.projection).expanduser().resolve()
    packet = read_json(packet_path, "review packet")
    projection = read_json(projection_path, "acceptance projection")
    if not isinstance(packet, dict) or packet.get("kind") not in ("review", "acceptance"):
        fail("handoff packet kind must be review or acceptance")
    phase_e_handoff = bool(getattr(args, "purpose", None) or packet.get("purpose") is not None)
    purpose = normalize_review_purpose(getattr(args, "purpose", None) or packet.get("purpose"), packet_kind=packet.get("kind"))
    if purpose in ("ticket_review", "critical_axis") and packet.get("kind") != "review":
        fail("ticket/critical review purpose requires a review packet")
    if purpose == "final_g5" and packet.get("kind") != "acceptance":
        fail("final_g5 purpose requires an acceptance packet")
    if packet.get("purpose") is not None and normalize_review_purpose(packet.get("purpose"), packet_kind=packet.get("kind")) != purpose:
        fail("declared review purpose does not match the packet purpose")
    root = schema()
    validate(packet, root["$defs"]["acceptance_packet" if packet.get("kind") == "acceptance" else "review_packet"], root, "$.packet")
    if projection.get("kind") != "acceptance_projection":
        fail("handoff projection kind must be acceptance_projection")
    validate(projection, schema()["$defs"]["acceptance_projection"], schema(), "$.projection")
    criteria = projection.get("criteria", [])
    criterion_ids = [item.get("id") for item in criteria]
    if not criteria or len(criterion_ids) != len(set(criterion_ids)) or any(not safe_id(str(i), "criterion_id") for i in criterion_ids):
        fail("projection must contain each active criterion exactly once")
    forbidden = {"worker_returns", "review_log", "repair_narrative", "commit_history", "self_rating", "tests_pass_summary", "credentials"}
    leaked = forbidden.intersection(projection)
    if leaked:
        fail(f"projection leaks forbidden history/self-rating fields: {sorted(leaked)}")
    with Lock(p["lock"]):
        state, _ = load_mutation_state(p, args.owner_token, args.revision)
        admit_event(state, "handoff.prepare")
        binding = current_intent_binding(state)
        if projection.get("intent_revision") != binding["revision"]:
            fail("acceptance projection is not the current intent revision")
        projection_ref = projection.get("intent_document_ref")
        projection_hash = projection.get("intent_document_hash")
        if projection_ref is not None and projection_ref != binding["document_ref"]:
            fail("acceptance projection intent document ref is stale")
        if projection_hash is not None and projection_hash != binding["document_hash"]:
            fail("acceptance projection intent document hash is stale")
        packet_identity_value = packet_identity(packet)
        if packet_identity_value.get("intent_revision") not in (None, binding["revision"]):
            fail("handoff packet intent revision is stale")
        if packet_identity_value.get("intent_document_ref") not in (None, binding["document_ref"]):
            fail("handoff packet intent document ref is stale")
        if packet_identity_value.get("intent_document_hash") not in (None, binding["document_hash"]):
            fail("handoff packet intent document hash is stale")
        active_criteria = {item["id"] for item in state.get("criteria", []) if item.get("status") == "active"}
        if set(criterion_ids) != active_criteria:
            fail("acceptance projection criteria do not match current active criteria")
        document = next((item for item in state.get("documents", []) if item.get("id") == binding["document_ref"]), None)
        if document is None:
            fail("current intent document is missing")
        document_path = Path(document["path"])
        if not document_path.exists() or sha256_file(document_path) != document.get("hash") or document.get("hash") != binding["document_hash"]:
            fail("current intent document hash does not match the ledger")
        candidate_attempt = next((item for item in state.get("attempts", []) if item.get("id") == args.attempt_id), None)
        if candidate_attempt is None or not candidate_attempt.get("candidate_sha"):
            fail("handoff requires a frozen candidate")
        if phase_e_handoff and (candidate_attempt.get("state") != "PREPARED" or candidate_attempt.get("return_ref")):
            fail("handoff requires a fresh PREPARED reviewer attempt")
        if packet_identity_value.get("attempt_id") != candidate_attempt.get("id"):
            fail("handoff packet attempt identity does not match the registered reviewer attempt")
        if purpose == "critical_axis":
            ticket = next((item for item in state.get("tickets", []) if item.get("id") == candidate_attempt.get("subject_ref")), None)
            if ticket is None or ticket.get("risk") != "critical":
                fail("critical-axis handoff requires a critical ticket")
        if projection.get("candidate_fingerprint") != candidate_attempt.get("candidate_sha"):
            fail("handoff projection candidate does not match the frozen candidate")
        if packet.get("subject_fingerprint") not in (None, candidate_attempt.get("candidate_sha")):
            fail("handoff packet subject is not the frozen candidate")
    export = safe_root(args.export_root, "export root")
    bundle = safe_root(args.bundle_root, "bundle root")
    if under(bundle, export) or under(export, bundle):
        fail("bundle and export roots may not contain one another")
    regular_directory(export, "export root")
    if bundle.exists() and (bundle.is_symlink() or not bundle.is_dir()):
        fail("bundle root is not a regular directory")
    if not export.is_dir():
        fail("export root does not exist")
    packet_raw = packet_path.read_bytes()
    packet_hash = sha256_bytes(packet_raw)
    manifest: list[dict[str, Any]] = []
    for path in sorted(export.rglob("*")):
        rel = path.relative_to(export)
        if any(part in {".git", ".autopilot", ".codex", ".agents", ".claude"} for part in rel.parts):
            continue
        if path.is_symlink():
            fail(f"export contains symlink: {rel}")
        if not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
            fail(f"export contains unsupported file type: {rel}")
        if path.is_file():
            data = path.read_bytes()
            manifest.append({"path": rel.as_posix(), "sha256": sha256_bytes(data), "bytes": len(data), "mode": stat.S_IMODE(path.stat().st_mode)})
    manifest_bytes = canonical_bytes({"candidate_fingerprint": projection.get("candidate_fingerprint"), "files": manifest})
    checklist = "# Operator checklist\n\nTransfer only this bundle. Start a new clean reviewer session; do not fork/resume author context. Record the packet/export hashes and environment/context receipts before running checks. Return exact structured JSON.\n"
    bundle_writes = (
        (bundle / "manifest.json", manifest_bytes),
        (bundle / "packet.json", canonical_bytes(packet)),
        (bundle / "projection.json", canonical_bytes(projection)),
        (bundle / "operator-checklist.md", checklist.encode()),
    )
    manifest_hash = sha256_bytes(manifest_bytes)
    def change(state: dict[str, Any]) -> None:
        admit_event(state, "handoff.prepare")
        attempt = attempt_by_id(state, args.attempt_id)
        if attempt["epoch"] != state["owner"]["epoch"]:
            fail("handoff attempt is stale")
        if attempt.get("kind") not in ("review", "acceptance"):
            fail("handoff requires a separate reviewer/acceptance attempt")
        active_plan = _ACTIVE_WRITE_PLAN.get()
        if active_plan is None:
            fail("handoff bundle writes require a locked immutable write plan")
        for destination, data in bundle_writes:
            active_plan.add(destination, data, "canonical")
        object_store(p, packet_raw)
        attempt["state"] = "PREPARED"
        attempt["kind"] = "review"
        attempt["mode"] = "user_assisted"
        if phase_e_handoff:
            attempt["review_purpose"] = purpose
        attempt["packet_ref"] = f"objects/{packet_hash}"
        attempt["packet_hash"] = packet_hash
        attempt["handoff"] = {"bundle_root": str(bundle), "manifest_ref": f"sha256:{manifest_hash}", "candidate_fingerprint": projection.get("candidate_fingerprint"), "intent_revision": projection.get("intent_revision"), "intent_document_ref": binding["document_ref"], "intent_document_hash": binding["document_hash"], "purpose": purpose, "packet_kind": packet.get("kind"), "projection_hash": sha256_bytes(canonical_bytes(projection)), "transport": "user_assisted", "context_grade": "MANUAL_ATTESTED_CLEAN"}
        add_usage(state.setdefault("usage", default_usage()).setdefault("counters", zero_usage()), {"manual_handoffs": 1, "manual_setup": 1, "user_interventions": 1})
        state["lifecycle"]["control"] = "BLOCKED"
        state["lifecycle"]["reason"] = "manual_review_pending"
        state["lifecycle"]["next_action"] = {"kind": "import_manual_review", "subject_refs": [args.attempt_id], "preconditions": ["environment receipt", "context receipt", "exact structured return", "integrity barrier"], "read_refs": ["phases/accept.md", "references/safety.md"]}
    result = transaction(p, args.owner_token, args.revision, change)
    return {"prepared": True, "bundle_root": str(bundle), "manifest_sha256": manifest_hash, "purpose": purpose, "revision": result["revision"], "transport": "user_assisted", "context_grade": "MANUAL_ATTESTED_CLEAN"}


def cmd_import_manual_legacy(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    env = read_json(Path(args.environment_receipt), "environment receipt")
    context = read_json(Path(args.context_receipt), "context receipt")
    validate_manual_receipt(env, "environment receipt")
    validate_manual_receipt(context, "context receipt")
    return_path = Path(args.return_file).expanduser().resolve()
    baseline_path = Path(args.integrity_receipt).expanduser().resolve()
    baseline = read_json(baseline_path, "integrity receipt")
    with Lock(p["lock"]):
        state, previous_raw = load_mutation_state(p, args.owner_token)
        if state.get("lifecycle", {}).get("control") in TERMINAL_CONTROLS:
            prior_attempt = next((item for item in state.get("attempts", []) if item.get("id") == args.attempt_id), None)
            if prior_attempt and prior_attempt.get("lease", {}).get("state") == "released":
                try:
                    retry_path = inbox_file(p, args.attempt_id, return_path)
                    retry_ref = f"objects/{sha256_file(retry_path)}"
                except (LedgerError, OSError):
                    retry_ref = None
                prior_acceptance = next((item for item in state.get("acceptance", []) if item.get("return_ref") == retry_ref), None)
                if (
                    retry_ref
                    and prior_attempt.get("return_ref") == retry_ref
                    and prior_acceptance is not None
                    and prior_acceptance.get("intent_revision") == args.intent_revision
                    and prior_acceptance.get("candidate_fingerprint") == args.candidate_fingerprint
                ):
                    return {"imported": True, "idempotent": True, "terminal": True, "verdict": prior_acceptance.get("verdict"), "acceptance_transport": "user_assisted", "context_grade": "MANUAL_ATTESTED_CLEAN", "release_ready": False, "revision": state["revision"]}
            admit_event(state, "acceptance.import")
        attempt = next((item for item in state.get("attempts", []) if item.get("id") == args.attempt_id), None)
        proposed_path = inbox_file(p, args.attempt_id, return_path)
        proposed_ref = f"objects/{sha256_file(proposed_path)}"
        prior_acceptance = next((item for item in state.get("acceptance", []) if item.get("return_ref") == proposed_ref), None)
        if attempt is not None and attempt.get("return_ref") == proposed_ref and prior_acceptance is not None:
            if prior_acceptance.get("intent_revision") != args.intent_revision or prior_acceptance.get("candidate_fingerprint") != args.candidate_fingerprint:
                fail("conflicting duplicate manual return binding")
            if attempt.get("lease", {}).get("state") == "released":
                return {"imported": True, "idempotent": True, "terminal": state["lifecycle"]["control"] in ("ACCEPTED", "FAILED", "CANCELLED"), "verdict": prior_acceptance.get("verdict"), "acceptance_transport": "user_assisted", "context_grade": "MANUAL_ATTESTED_CLEAN", "release_ready": False, "revision": state["revision"]}
            admit_event(state, "acceptance.import")
            next_state = copy.deepcopy(state)
            attempt_by_id(next_state, args.attempt_id)["lease"]["state"] = "released"
            next_state["revision"] += 1
            next_state["previous_publication_hash"] = sha256_bytes(previous_raw)
            next_state["updated_at"] = now()
            publish(p, next_state, previous_raw, "manual-import-reconcile")
            return {"imported": True, "idempotent": True, "reconciled": True, "verdict": prior_acceptance.get("verdict"), "acceptance_transport": "user_assisted", "context_grade": "MANUAL_ATTESTED_CLEAN", "release_ready": False, "revision": next_state["revision"]}
        admit_event(state, "acceptance.import")
        if attempt is None:
            attempt = attempt_by_id(state, args.attempt_id)
        if state["revision"] != args.revision:
            fail(f"revision mismatch: expected {args.revision}, current {state['revision']}")
        if attempt.get("mode") != "user_assisted":
            fail("manual import requires a user-assisted prepared attempt")
        if attempt.get("kind") != "review":
            fail("manual import requires a separate reviewer attempt")
        binding = current_intent_binding(state)
        if args.intent_revision != binding["revision"]:
            fail("manual import intent revision is not current")
        packet = stored_payload(p, attempt.get("packet_ref"), "acceptance packet")
        root = schema()
        validate(packet, root["$defs"]["acceptance_packet"], root, "$.acceptance_packet")
        if context.get("packet_hash") != attempt.get("packet_hash"):
            fail("context receipt packet hash does not match prepared handoff")
        expected_manifest = (attempt.get("handoff") or {}).get("manifest_ref")
        if expected_manifest and context.get("export_hash") != expected_manifest.removeprefix("sha256:"):
            fail("context receipt export hash does not match prepared handoff")
        verify_manual_inventory(env, attempt.get("handoff") or {})
        payload, digest, return_raw = ingest_payload(p, state, args.attempt_id, return_path, attempt.get("packet_hash"), "acceptance")
        identity = packet_identity(payload)
        if identity.get("intent_revision") != args.intent_revision:
            fail("manual return intent revision mismatch")
        if identity.get("intent_document_ref") not in (None, binding["document_ref"]):
            fail("manual return intent document ref mismatch")
        if identity.get("intent_document_hash") not in (None, binding["document_hash"]):
            fail("manual return intent document hash mismatch")
        if identity.get("epoch") not in (None, attempt.get("epoch")):
            fail("manual return epoch mismatch")
        candidate = args.candidate_fingerprint
        if payload.get("candidate_fingerprint") != candidate:
            fail("manual return candidate fingerprint mismatch")
        if packet.get("subject_fingerprint") != candidate:
            fail("manual acceptance packet subject is not the current candidate")
        if payload.get("verdict") not in ("PASS", "BLOCK", "UNVERIFIABLE"):
            fail("manual return has invalid verdict")
        packet_required = [review_criterion_id(item) for item in packet.get("criteria", [])]
        required = [x for x in args.required_criteria.split(",") if x]
        if required != packet_required and set(required) != set(packet_required):
            fail("required criteria argument does not match the prepared acceptance packet")
        required = packet_required
        check_integrity(baseline, state, p["ledger"].read_bytes(), candidate)
        validate_acceptance_return_semantics(payload, required)
        add_usage(state.setdefault("usage", default_usage()).setdefault("counters", zero_usage()), {"return_bytes": len(canonical_bytes(payload)), "manual_wait": 1})
        existing_ref = f"objects/{digest}"
        if any(item.get("return_ref") == existing_ref for item in state.get("acceptance", [])):
            if state["lifecycle"]["control"] in ("ACCEPTED", "FAILED", "CANCELLED"):
                return {"imported": True, "idempotent": True, "terminal": True, "verdict": payload.get("verdict"), "acceptance_transport": "user_assisted", "context_grade": "MANUAL_ATTESTED_CLEAN", "release_ready": False, "revision": state["revision"]}
            if payload.get("verdict") == "PASS":
                next_state = copy.deepcopy(state)
                next_attempt = attempt_by_id(next_state, args.attempt_id)
                next_attempt["lease"]["state"] = "released"
                ticket = next((t for t in next_state.get("tickets", []) if t.get("id") == next_attempt.get("subject_ref")), None)
                if ticket and ticket.get("state") == "REVIEW":
                    ticket["state"] = "INTEGRATED"
                next_state["revision"] += 1
                next_state["previous_publication_hash"] = sha256_bytes(previous_raw)
                next_state["updated_at"] = now()
                publish(p, next_state, previous_raw)
                return {"imported": True, "idempotent": True, "reconciled": True, "verdict": payload.get("verdict"), "acceptance_transport": "user_assisted", "context_grade": "MANUAL_ATTESTED_CLEAN", "release_ready": False, "revision": next_state["revision"]}
            return {"imported": True, "idempotent": True, "verdict": payload.get("verdict"), "acceptance_transport": "user_assisted", "context_grade": "MANUAL_ATTESTED_CLEAN", "release_ready": False}
        next_state = copy.deepcopy(state)
        next_attempt = attempt_by_id(next_state, args.attempt_id)
        next_attempt["state"] = "RETURNED"
        next_attempt["return_ref"] = f"objects/{digest}"
        next_attempt["lease"]["state"] = "released"
        if payload.get("verdict") == "PASS":
            ticket = next((t for t in next_state.get("tickets", []) if t.get("id") == next_attempt.get("subject_ref")), None)
            if ticket and ticket.get("state") == "REVIEW":
                ticket["state"] = "INTEGRATED"
        acceptance = next_state.setdefault("acceptance", [])
        environment_raw = canonical_bytes(env)
        context_raw = canonical_bytes(context)
        acceptance.append({"round": len(acceptance) + 1, "intent_revision": args.intent_revision, "candidate_fingerprint": candidate, "verdict": payload.get("verdict"), "transport": "user_assisted", "context_grade": "MANUAL_ATTESTED_CLEAN", "setup_receipt_ref": f"objects/{sha256_bytes(environment_raw)}", "context_receipt_ref": f"objects/{sha256_bytes(context_raw)}", "return_ref": f"objects/{digest}", "outcome_refs": []})
        evidence = next_state.setdefault("evidence", [])
        add_usage(next_state.setdefault("usage", default_usage()).setdefault("counters", zero_usage()), {"return_bytes": len(canonical_bytes(payload))})
        evidence.append({"id": f"ev-{digest[:16]}", "hash": digest, "source": "manual_review_return", "scenario": "critical/G5", "outcome": payload.get("verdict"), "observer": "independent-reviewer", "subject": candidate})
        if payload.get("verdict") == "PASS":
            next_state["lifecycle"]["phase"] = "ACCEPT"
            next_state["lifecycle"]["control"] = "ACTIVE"
            next_state["lifecycle"]["reason"] = None
            next_state["lifecycle"]["next_action"] = {"kind": "g6_final_record", "subject_refs": [args.attempt_id], "preconditions": ["current revisions unchanged", "no active leases/blockers"], "read_refs": ["phases/accept.md", "references/ledger.md"]}
        else:
            next_state["lifecycle"]["control"] = "BLOCKED"
            next_state["lifecycle"]["reason"] = "manual_review_not_pass"
        next_state["revision"] += 1
        next_state["previous_publication_hash"] = sha256_bytes(previous_raw)
        next_state["updated_at"] = now()
        validate_ledger(next_state, verify_files=False)
        object_store(p, return_raw)
        object_store(p, environment_raw)
        object_store(p, context_raw)
        publish(p, next_state, previous_raw)
    return {"imported": True, "idempotent": False, "verdict": payload.get("verdict"), "acceptance_transport": "user_assisted", "context_grade": "MANUAL_ATTESTED_CLEAN", "release_ready": False, "revision": next_state["revision"]}


def cmd_import_manual(args: argparse.Namespace) -> dict[str, Any]:
    """Import an explicit-purpose manual result through the Phase E review lifecycle."""
    if not getattr(args, "purpose", None):
        return cmd_import_manual_legacy(args)
    purpose = normalize_review_purpose(args.purpose)
    p = paths(args.control_root, args.run_id)
    env = read_json(Path(args.environment_receipt), "environment receipt")
    context = read_json(Path(args.context_receipt), "context receipt")
    integrity = read_json(Path(args.integrity_receipt), "integrity receipt")
    root = schema()
    validate(env, root["$defs"]["environment_receipt"], root, "$.environment_receipt")
    validate(context, root["$defs"]["context_receipt"], root, "$.context_receipt")
    validate_manual_receipt(env, "environment receipt")
    validate_manual_receipt(context, "context receipt")
    if context.get("reviewer_stopped") is not True:
        fail("manual review import requires explicit reviewer stop evidence")
    return_path = Path(args.return_file).expanduser().resolve()
    with Lock(p["lock"]):
        state, previous_raw = load_mutation_state(p, args.owner_token, args.revision)
        admit_event(state, "acceptance.import")
        attempt = attempt_by_id(state, args.attempt_id)
        if attempt.get("state") != "PREPARED" or attempt.get("return_ref"):
            fail("manual review import requires a fresh PREPARED attempt; interrupted/lost/returned attempts are immutable")
        if attempt.get("epoch") != state.get("owner", {}).get("epoch"):
            fail("manual review attempt epoch is stale")
        if attempt.get("mode") != "user_assisted" or attempt.get("kind") != "review":
            fail("manual import requires the prepared user-assisted reviewer attempt")
        handoff = attempt.get("handoff") or {}
        if handoff.get("purpose") != purpose:
            fail("manual import purpose does not match the prepared handoff")
        if attempt.get("review_purpose") not in (None, purpose):
            fail("manual import purpose does not match the registered attempt")
        packet = stored_payload(p, attempt.get("packet_ref"), "manual review packet")
        packet_kind = handoff.get("packet_kind") or packet.get("kind")
        expected_kind = "acceptance" if purpose == "final_g5" else "review"
        if packet_kind != expected_kind or packet.get("kind") != expected_kind:
            fail("manual import packet type does not match its review purpose")
        packet_purpose = packet.get("purpose")
        if packet_purpose is not None and normalize_review_purpose(packet_purpose, packet_kind=packet_kind) != purpose:
            fail("manual import purpose conflicts with the immutable packet")
        binding = current_intent_binding(state)
        if args.intent_revision != binding["revision"] or handoff.get("intent_revision") != binding["revision"]:
            fail("manual import intent revision is stale")
        if args.candidate_fingerprint != attempt.get("candidate_sha") or handoff.get("candidate_fingerprint") != attempt.get("candidate_sha"):
            fail("manual import candidate is not the prepared frozen candidate")
        if packet.get("subject_fingerprint") != attempt.get("candidate_sha"):
            fail("manual import packet subject is not the prepared frozen candidate")
        if context.get("packet_hash") != attempt.get("packet_hash"):
            fail("context receipt packet hash does not match prepared handoff")
        expected_manifest = handoff.get("manifest_ref", "").removeprefix("sha256:")
        if context.get("export_hash") != expected_manifest:
            fail("context receipt export hash does not match prepared handoff")
        verify_manual_inventory_exact(env, handoff)
        check_integrity(integrity, state, previous_raw, attempt.get("candidate_sha"))
        return_kind = "acceptance" if packet_kind == "acceptance" else "review"
        payload, digest, return_raw = ingest_payload(
            p, state, args.attempt_id, return_path, attempt.get("packet_hash"), return_kind
        )
        identity = packet_identity(payload)
        if identity.get("intent_revision") != args.intent_revision:
            fail("manual return intent revision mismatch")
        if identity.get("epoch") != attempt.get("epoch"):
            fail("manual return epoch mismatch")
        required = [item for item in args.required_criteria.split(",") if item]
        packet_required = [review_criterion_id(item) for item in packet.get("criteria", [])]
        if set(required) != set(packet_required):
            fail("required criteria argument does not match the prepared manual packet")
        if return_kind == "acceptance":
            validate_acceptance_return_semantics(payload, packet_required)
            if payload.get("candidate_fingerprint") != attempt.get("candidate_sha"):
                fail("manual acceptance return candidate fingerprint mismatch")
        else:
            validate_review_return_semantics(payload, packet)
            if payload.get("subject_fingerprint") != attempt.get("candidate_sha"):
                fail("manual review return subject fingerprint mismatch")
        if payload.get("verdict") in ("BLOCK", "UNVERIFIABLE") and not any(
            item.get("impact") == "blocking" for item in payload.get("findings", [])
        ):
            fail("manual BLOCK/UNVERIFIABLE must materialize at least one blocking repairable finding")

        next_state = copy.deepcopy(state)
        next_attempt = attempt_by_id(next_state, args.attempt_id)
        next_attempt["state"] = "RETURNED"
        next_attempt["return_ref"] = f"objects/{digest}"
        next_attempt["return_source_revision"] = identity.get("source_revision", next_attempt.get("packet_source_revision"))
        next_attempt["review_result"] = payload.get("verdict")
        next_attempt["lease"]["state"] = "released"
        next_attempt["finding_refs"] = append_review_findings(
            next_state, payload, next_attempt["id"], digest, packet=packet, subject_ref=next_attempt.get("subject_ref")
        )
        integrity_raw = canonical_bytes(integrity)
        env_raw = canonical_bytes(env)
        context_raw = canonical_bytes(context)
        integrity_ref = f"objects/{sha256_bytes(integrity_raw)}"
        review_id = f"REV-{digest[:16]}"
        next_state.setdefault("reviews", []).append({
            "id": review_id, "attempt_ref": next_attempt["id"], "purpose": purpose,
            "mandate": packet.get("mandate", purpose),
            "subject_fingerprint": attempt.get("candidate_sha"), "verdict": payload.get("verdict"),
            "accepted": True, "return_ref": f"objects/{digest}", "integrity_ref": integrity_ref,
            "context_refs": payload.get("context_refs", [context.get("receipt_id")]),
            "finding_refs": next_attempt["finding_refs"],
            "finding_resolution": copy.deepcopy(payload.get("finding_resolution", [])),
            "intent_revision": binding["revision"], "reviewer_identity": context.get("receipt_id"),
            "reviewer_role": "manual-independent-reviewer", "review_kind": None,
            "target_artifact_refs": [], "target_artifact_versions": [], "target_revision": None,
            "invalidated_by": [],
        })
        qualification = append_review_qualification(
            next_state, next_attempt.get("subject_ref"), attempt.get("candidate_sha"),
            purpose=purpose, created_revision=state["revision"] + 1,
        )
        ticket = next((item for item in next_state.get("tickets", []) if item.get("id") == next_attempt.get("subject_ref")), None)
        finding_refs = next_attempt["finding_refs"]
        if payload.get("verdict") in ("BLOCK", "UNVERIFIABLE"):
            issue_id = append_issue(next_state, {
                "type": "manual_review_verdict", "cause": "oracle", "impact": "blocking",
                "affected_refs": [next_attempt.get("subject_ref")], "expected": "PASS",
                "actual": payload.get("verdict"), "disposition": "repair and fresh review required",
                "resolution_condition": "all manual findings repaired and a fresh purpose-matching review passes",
            }, source_ref=review_id)
            next_state["lifecycle"]["phase"] = "VERIFY" if purpose == "final_g5" else next_state["lifecycle"].get("phase")
            next_state["lifecycle"]["control"] = "BLOCKED"
            next_state["lifecycle"]["reason"] = "manual_review_not_pass"
            next_state["lifecycle"]["issue_refs"] = sorted(set(next_state["lifecycle"].get("issue_refs", []) + [issue_id]))
            next_state["lifecycle"]["next_action"] = {
                "kind": "authorize_repair", "subject_refs": [next_attempt.get("subject_ref"), *finding_refs],
                "preconditions": ["bind repair to each current manual finding", "fresh review required after a new candidate"],
                "read_refs": ["phases/execute.md", "phases/accept.md"],
            }
            if purpose == "final_g5":
                next_state.setdefault("repair_waves", []).append({
                    "id": f"G5-WAVE-{digest[:16]}",
                    "source_qualification_ref": qualification["id"],
                    "source_candidate_fingerprint": attempt.get("candidate_sha"),
                    "finding_refs": sorted(finding_refs), "state": "OPEN",
                    "repaired_candidate_fingerprint": None, "final_g5_qualification_ref": None,
                    "created_revision": state["revision"] + 1, "closed_revision": None,
                })
        elif purpose == "final_g5":
            if qualification.get("result") != "PASS":
                fail("final G5 PASS conflicts with another accepted result for this candidate; repair and use a fresh candidate")
            if any(item.get("state") != "INTEGRATED" for item in next_state.get("tickets", []) if item.get("state") != "CANCELLED"):
                fail("final G5 requires every current ticket to be integrated")
            if any(effect_is_unresolved(item) for item in next_state.get("operations", [])):
                fail("final G5 is blocked by an unresolved durable effect")
            open_waves = [item for item in next_state.get("repair_waves", []) if item.get("state") == "OPEN"]
            projection = finding_obligation_projection(next_state)
            status_by_finding = {item.get("finding_ref"): item.get("status") for item in projection.get("items", [])}
            for wave in open_waves:
                if wave.get("source_candidate_fingerprint") == attempt.get("candidate_sha"):
                    fail("G5 repair wave requires a fresh repaired candidate before final re-review")
                if any(status_by_finding.get(ref) not in ("resolved", "superseded") for ref in wave.get("finding_refs", [])):
                    fail("G5 repair wave findings are not fully resolved on the fresh candidate")
                wave["state"] = "CLOSED"
                wave["repaired_candidate_fingerprint"] = attempt.get("candidate_sha")
                wave["final_g5_qualification_ref"] = qualification["id"]
                wave["closed_revision"] = state["revision"] + 1
            next_state["lifecycle"]["phase"] = "ACCEPT"
            next_state["lifecycle"]["control"] = "ACTIVE"
            next_state["lifecycle"]["reason"] = None
            next_state["lifecycle"]["next_action"] = {
                "kind": "g6_final_record", "subject_refs": [qualification["id"]],
                "preconditions": ["final G5 qualification remains current", "no active leases/blockers/effects"],
                "read_refs": ["phases/accept.md", "references/ledger.md"],
            }
        else:
            next_state["lifecycle"]["control"] = "ACTIVE"
            next_state["lifecycle"]["reason"] = f"manual_{purpose}_qualified"
            next_state["lifecycle"]["next_action"] = {
                "kind": "integrate_candidate" if ticket and ticket.get("state") != "INTEGRATED" else "continue_after_manual_review",
                "subject_refs": [qualification["id"]],
                "preconditions": ["consume only the current qualification aggregate"],
                "read_refs": ["phases/execute.md"],
            }
        if purpose == "final_g5":
            next_state.setdefault("acceptance", []).append({
                "round": len(next_state.get("acceptance", [])) + 1,
                "attempt_ref": next_attempt["id"], "purpose": "final_g5",
                "intent_revision": binding["revision"], "candidate_fingerprint": attempt.get("candidate_sha"),
                "verdict": payload.get("verdict"), "transport": "user_assisted",
                "context_grade": "MANUAL_ATTESTED_CLEAN",
                "setup_receipt_ref": f"objects/{sha256_bytes(env_raw)}",
                "context_receipt_ref": f"objects/{sha256_bytes(context_raw)}",
                "integrity_ref": integrity_ref, "return_ref": f"objects/{digest}",
                "qualification_ref": qualification["id"], "finding_refs": finding_refs,
                "outcome_refs": finding_refs,
            })
        evidence = next_state.setdefault("evidence", [])
        evidence.append({
            "id": f"ev-{digest[:16]}", "hash": digest, "source": "manual_review_return",
            "scenario": purpose, "outcome": payload.get("verdict"),
            "observer": "independent-reviewer", "subject": attempt.get("candidate_sha"),
        })
        add_usage(next_state.setdefault("usage", default_usage()).setdefault("counters", zero_usage()), {
            "return_bytes": len(return_raw), "manual_wait": 1,
        })
        next_state["revision"] += 1
        next_state["previous_publication_hash"] = sha256_bytes(previous_raw)
        next_state["updated_at"] = now()
        validate_ledger(next_state, verify_files=False)
        for raw in (return_raw, env_raw, context_raw, integrity_raw):
            object_store(p, raw)
        publish(p, next_state, previous_raw)
    return {
        "imported": True, "idempotent": False, "purpose": purpose,
        "verdict": payload.get("verdict"), "qualification_ref": qualification["id"],
        "acceptance_transport": "user_assisted", "context_grade": "MANUAL_ATTESTED_CLEAN",
        "release_ready": False, "revision": next_state["revision"],
    }


def cmd_publish_intent(args: argparse.Namespace) -> dict[str, Any]:
    """Publish the one initial intent binding for an initialized run."""
    p = paths(args.control_root, args.run_id)
    raw = intent_source_bytes(args.intent_file)
    digest = sha256_bytes(raw)
    doc_id = safe_id(args.doc_id, "document_id")
    doc_path = canonical_document_path(p, doc_id, args.doc_version)
    intent_revision = nonempty_string(args.intent_revision, "intent_revision")
    started = time.monotonic()

    with Lock(p["lock"]):
        state, previous_raw = load_mutation_state(p, args.owner_token, args.revision)
        admit_event(state, "intent.publish")
        if state.get("intent") is not None:
            fail("initial intent already exists; use amend for a new intent revision")
        if any(document.get("kind") == "intent" for document in state.get("documents", [])):
            fail("an intent document already exists without a current binding; recover or adjudicate it before bootstrap")
        if state["lifecycle"]["phase"] not in ("PREFLIGHT", "INTENT"):
            fail("initial intent may only be published from PREFLIGHT or INTENT")
        current_control = state["lifecycle"]["control"]
        if current_control not in ("ACTIVE", "BLOCKED", "RECOVERING"):
            fail("initial intent requires an ACTIVE, BLOCKED, or RECOVERING run; resume/recover the run first")

        next_state = copy.deepcopy(state)
        next_state.setdefault("documents", []).append({
            "id": doc_id,
            "version": args.doc_version,
            "path": str(doc_path),
            "hash": digest,
            "kind": "intent",
            "section_anchors": [],
        })
        next_state["intent"] = {
            "current_revision": intent_revision,
            "document_ref": doc_id,
            "document_hash": digest,
            "approved_amendments": [],
            "acceptance_policy": "automatic",
            "checkpoint_policy": "gate",
            "prior_accepted_refs": [],
        }
        blocking_refs = list(next_state["lifecycle"].get("issue_refs", []))
        recovering = current_control == "RECOVERING" and not blocking_refs
        next_state["lifecycle"]["phase"] = "INTENT"
        next_state["lifecycle"]["control"] = "BLOCKED" if blocking_refs else ("RECOVERING" if recovering else "ACTIVE")
        next_state["lifecycle"]["reason"] = "existing_blockers" if blocking_refs else ("initial_intent_published_during_recovery" if recovering else "initial_intent_published")
        next_state["lifecycle"]["next_action"] = {
            "kind": "resolve_blockers_before_g1" if blocking_refs else ("finish_recovery_then_g1" if recovering else "g1_build"),
            "subject_refs": [doc_id, *blocking_refs],
            "preconditions": ["current intent hash verified"],
            "read_refs": ["phases/intent.md", "references/ledger.md"],
        }

        usage = next_state.setdefault("usage", default_usage())
        usage.setdefault("counters", zero_usage())
        usage.setdefault("trace", [])
        usage.setdefault("shared_setup", zero_usage())
        usage.setdefault("gate_costs", {f"G{i}": zero_usage() for i in range(7)})
        delta = {field: 0 for field in USAGE_FIELDS}
        delta["helper_calls"] = 1
        delta["internal_publications"] = 1
        delta["wall_time_ms"] = max(0, int((time.monotonic() - started) * 1000))
        add_usage(usage["counters"], delta)
        usage["trace"].append({
            "id": f"trace-{state['revision'] + 1}-helper",
            "kind": "helper_publication",
            "actor": "ledger-helper",
            "subject_ref": next_state["lifecycle"]["next_action"]["kind"],
            "delta": delta,
            "evidence_ref": None,
            "recorded_at": now(),
        })
        next_state["revision"] = state["revision"] + 1
        next_state["previous_publication_hash"] = sha256_bytes(previous_raw)
        next_state["updated_at"] = now()

        # Validate every input and the complete proposed ledger before making
        # the immutable document visible.  A same-byte orphan from a crash is
        # reusable; conflicting bytes are never overwritten.
        validate_ledger(next_state)
        if doc_path.exists():
            regular_non_symlink(doc_path)
            if doc_path.read_bytes() != raw:
                fail("canonical initial intent destination already exists with different bytes")
        else:
            atomic_create(doc_path, raw)
        publish(p, next_state, previous_raw)

    return {
        "published": True,
        "intent_revision": intent_revision,
        "document_ref": doc_id,
        "document_hash": digest,
        "revision": next_state["revision"],
        "phase": next_state["lifecycle"]["phase"],
        "control": next_state["lifecycle"]["control"],
        "next_action": next_state["lifecycle"]["next_action"],
    }


def cmd_adopt_requirements(args: argparse.Namespace) -> dict[str, Any]:
    """Atomically publish explicit requirements/criteria into a legacy run."""
    p = paths(args.control_root, args.run_id)
    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest = read_json(manifest_path, "requirements manifest")
    root = schema()
    validate(manifest, root["$defs"]["requirements_manifest"], root, "$.requirements_manifest")
    raw = manifest_path.read_bytes()
    digest = sha256_bytes(raw)
    requirement_ids = ids_from_records(manifest["requirements"], "id", "requirement")
    criterion_ids = ids_from_records(manifest["criteria"], "id", "criterion")
    requirement_set, criterion_set = set(requirement_ids), set(criterion_ids)
    if requirement_set & criterion_set:
        fail("requirements manifest reuses an ID across requirements and criteria")
    for requirement in manifest["requirements"]:
        if not set(requirement.get("criterion_refs", [])).issubset(criterion_set):
            fail(f"requirements manifest has an unknown criterion binding: {requirement['id']}")
        if manifest["intent_document_ref"] not in requirement.get("provenance_refs", []):
            fail(f"requirement lacks explicit current-intent provenance: {requirement['id']}")
    for criterion in manifest["criteria"]:
        if not criterion.get("requirement_refs") or not set(criterion["requirement_refs"]).issubset(requirement_set):
            fail(f"criterion lacks a valid explicit requirement binding: {criterion['id']}")
        if criterion.get("source_ref") not in (None, manifest["intent_document_ref"]):
            fail(f"criterion source_ref is not the bound intent document: {criterion['id']}")
        for requirement_ref in criterion["requirement_refs"]:
            requirement = next(item for item in manifest["requirements"] if item["id"] == requirement_ref)
            if criterion["id"] not in requirement.get("criterion_refs", []):
                fail(f"requirement/criterion binding is not bidirectional: {criterion['id']}")

    with Lock(p["lock"]):
        state, previous_raw = load_mutation_state(p, args.owner_token)
        if state["owner"]["token"] != args.owner_token:
            fail("owner token mismatch; stale orchestrator is fenced")
        existing_publication = next((item for item in state.get("requirements_publications", []) if item.get("id") == manifest["publication_id"]), None)
        if existing_publication:
            if existing_publication.get("publication_hash") == digest:
                current_binding = current_intent_binding(state)
                if existing_publication.get("status") == "PUBLISHED" and (existing_publication.get("intent_revision"), existing_publication.get("intent_document_ref"), existing_publication.get("intent_document_hash")) == (current_binding["revision"], current_binding["document_ref"], current_binding["document_hash"]):
                    return {"published": True, "idempotent": True, "publication_id": manifest["publication_id"], "publication_hash": digest, "revision": state["revision"], "next_action": state["lifecycle"]["next_action"]}
                fail("requirements publication is historical/stale; use a new publication ID bound to the current intent")
            fail("requirements publication ID already exists with different bytes")
        if state["revision"] != args.revision:
            fail(f"revision mismatch: expected {args.revision}, current {state['revision']}")
        if state["lifecycle"]["control"] in ("ACCEPTED", "FAILED", "CANCELLED"):
            fail("terminal run is immutable; start a successor run")
        admit_event(state, "requirements.adopt")
        if state["lifecycle"]["phase"] not in ("INTENT", "DESIGN", "PLAN"):
            fail("requirements adoption is only legal before execution")
        if state["lifecycle"]["phase"] == "PLAN" and state["lifecycle"].get("control") != "BLOCKED":
            fail("requirements adoption during PLAN requires an explicit repair blocker")
        if active_publication_leases(state):
            fail("requirements adoption requires stopped attempts and released leases")
        if any(effect_is_unresolved(item) for item in state.get("operations", [])):
            fail("requirements adoption requires reconciled operations")
        binding = current_intent_binding(state)
        if any(item.get("status") == "PUBLISHED" and item.get("intent_revision") == binding["revision"] and item.get("intent_document_hash") == binding["document_hash"] for item in state.get("requirements_publications", [])):
            fail("a current requirements publication already exists for this intent")
        if manifest["epoch"] != state["owner"]["epoch"]:
            fail("requirements manifest epoch does not match current owner")
        if (manifest["intent_revision"], manifest["intent_document_ref"], manifest["intent_document_hash"]) != (binding["revision"], binding["document_ref"], binding["document_hash"]):
            fail("requirements manifest is bound to a stale intent")
        collections = {
            "requirements": {item["id"]: item for item in state.get("requirements", [])},
            "criteria": {item["id"]: item for item in state.get("criteria", [])},
        }
        occupied = {item.get("id") for value in state.values() if isinstance(value, list) for item in value if isinstance(item, dict) and item.get("id")}
        for name in ("requirements", "criteria"):
            for record in manifest[name]:
                existing = collections[name].get(record["id"])
                if record["id"] in occupied and existing is None:
                    fail(f"requirements manifest ID conflicts with immutable state: {record['id']}")
                if existing is not None and existing != record:
                    fail(f"conflicting canonical {name[:-1]}: {record['id']}")

        next_state = copy.deepcopy(state)
        for name in ("requirements", "criteria"):
            target = next_state.setdefault(name, [])
            existing_ids = {item["id"] for item in target}
            target.extend(copy.deepcopy(item) for item in manifest[name] if item["id"] not in existing_ids)
        publication = {
            "id": manifest["publication_id"], "version": manifest["version"], "status": "PUBLISHED", "owner_epoch": state["owner"]["epoch"],
            "intent_revision": binding["revision"], "intent_document_ref": binding["document_ref"], "intent_document_hash": binding["document_hash"],
            "publication_hash": digest, "manifest_ref": f"objects/{digest}", "published_revision": state["revision"] + 1,
            "requirement_refs": requirement_ids, "criterion_refs": criterion_ids,
        }
        next_state.setdefault("requirements_publications", []).append(publication)
        provenance = ensure_runtime_provenance(next_state)
        migration_id = f"adopt-requirements-{manifest['publication_id']}"
        provenance["applied_migrations"].append({"id": migration_id, "helper_version": SKILL_VERSION, "applied_revision": state["revision"] + 1, "manifest_hash": digest, "object_ref": f"objects/{digest}"})
        next_state["lifecycle"]["next_action"] = {"kind": "publish_design_bundle", "subject_refs": [manifest["publication_id"]], "preconditions": ["requirements/criteria publication is current", "design bundle refs resolve exactly"], "read_refs": ["phases/design.md", "references/ledger.md"]}
        next_state["revision"] = state["revision"] + 1
        next_state["previous_publication_hash"] = sha256_bytes(previous_raw)
        next_state["updated_at"] = now()
        validate_ledger(next_state, verify_files=False)
        object_store(p, raw)
        publish(p, next_state, previous_raw, "requirements-adoption")
    return {"published": True, "idempotent": False, "publication_id": manifest["publication_id"], "publication_hash": digest, "requirement_count": len(requirement_ids), "criterion_count": len(criterion_ids), "revision": next_state["revision"], "next_action": next_state["lifecycle"]["next_action"]}


def current_design_publication(state: dict[str, Any]) -> dict[str, Any]:
    publication = state.get("design_publication")
    if not isinstance(publication, dict) or publication.get("status") != "PUBLISHED":
        fail("G2/G3 requires a published design bundle")
    validate_ledger(state)
    return publication


def design_publication_history(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Return publication history, presenting a legacy current record as item one."""
    history = state.get("design_publication_history")
    if isinstance(history, list) and history:
        return history
    publication = state.get("design_publication")
    return [copy.deepcopy(publication)] if isinstance(publication, dict) else []


def design_publication_requires_revision(state: dict[str, Any], publication: dict[str, Any]) -> bool:
    fingerprint = publication.get("publication_hash")
    publication_id = publication.get("id")
    blocked_reviews = {
        "BLOCK", "UNVERIFIABLE"
    }
    if any(
        review.get("subject_fingerprint") == fingerprint
        and review.get("verdict") in blocked_reviews
        and review.get("review_kind") in ("coverage", "plan")
        for review in state.get("reviews", [])
    ):
        return True
    if any(
        attempt.get("subject_ref") == publication_id
        and attempt.get("subject_fingerprint") == fingerprint
        and attempt.get("review_result") in blocked_reviews
        and attempt.get("mode") in ("coverage", "plan")
        for attempt in state.get("attempts", [])
    ):
        return True
    return state.get("lifecycle", {}).get("control") == "BLOCKED" and state.get("lifecycle", {}).get("reason") in {
        "review_not_pass", "design_review_blocked", "design_review_unverifiable", "design_revision_required"
    }


def active_publication_leases(state: dict[str, Any]) -> list[str]:
    return [
        attempt.get("id", "unknown")
        for attempt in state.get("attempts", [])
        if attempt.get("state") in ("PREPARED", "DISPATCHED")
        or attempt.get("lease", {}).get("state") in ("active", "quarantined")
    ]


def publication_consumer_refs(state: dict[str, Any], publication: dict[str, Any]) -> list[str]:
    subjects = {publication.get("id"), *publication.get("document_refs", []), *publication.get("requirement_refs", []), *publication.get("criterion_refs", []), *publication.get("contract_refs", []), *publication.get("ticket_refs", []), *publication.get("route_refs", [])}
    refs = set(item for item in subjects if item)
    changed = True
    while changed:
        changed = False
        for collection in ("attempts", "reviews", "findings", "issues", "evidence"):
            for item in state.get(collection, []):
                related = (
                    item.get("subject_ref") in refs
                    or item.get("subject") in refs
                    or item.get("subject_fingerprint") == publication.get("publication_hash")
                    or item.get("source_ref") in refs
                    or bool(set(item.get("affected_refs", [])) & refs)
                    or bool(set(item.get("finding_refs", [])) & refs)
                )
                if related and item.get("id") and item["id"] not in refs:
                    refs.add(item["id"])
                    changed = True
    return sorted(refs)


def supersede_design_publication(next_state: dict[str, Any], previous: dict[str, Any], replacement_id: str) -> None:
    """Keep old publication/review bytes intact while fencing their consumers."""
    old_id = previous["id"]
    history = next_state.setdefault("design_publication_history", [])
    old_history = next((item for item in history if item.get("id") == old_id), None)
    if old_history is None:
        old_history = copy.deepcopy(previous)
        history.append(old_history)
    old_history["status"] = "SUPERSEDED"
    old_history["superseded_by"] = replacement_id
    if replacement_id not in old_history.setdefault("invalidated_by", []):
        old_history["invalidated_by"].append(replacement_id)
    consumers = publication_consumer_refs(next_state, previous)
    old_history["consumer_refs"] = consumers
    consumer_set = set(consumers)
    subject_set = {old_id, *previous.get("document_refs", []), *previous.get("requirement_refs", []), *previous.get("criterion_refs", []), *previous.get("contract_refs", []), *previous.get("ticket_refs", []), *previous.get("route_refs", [])}
    for collection in ("attempts", "reviews", "findings", "evidence"):
        for item in next_state.get(collection, []):
            if item.get("id") in consumer_set and replacement_id not in item.setdefault("invalidated_by", []):
                item["invalidated_by"].append(replacement_id)
    for issue in next_state.get("issues", []):
        affected = set(issue.get("affected_refs", []))
        if issue.get("type") in ("review_verdict", "review_finding", "reviewer_disagreement") and (
            bool(affected & (subject_set | consumer_set)) or issue.get("source_ref") in consumer_set
        ):
            issue["impact"] = "advisory"
            issue["disposition"] = "historical evidence; superseded by revised design publication"
            if replacement_id not in issue.setdefault("invalidated_by", []):
                issue["invalidated_by"].append(replacement_id)
    next_state["lifecycle"]["issue_refs"] = [
        ref for ref in next_state["lifecycle"].get("issue_refs", [])
        if next((item for item in next_state.get("issues", []) if item.get("id") == ref), {}).get("impact") == "blocking"
    ]
    if next_state["lifecycle"].get("control") == "BLOCKED" and not any(item.get("impact") == "blocking" for item in next_state.get("issues", [])):
        next_state["lifecycle"]["control"] = "ACTIVE"
        next_state["lifecycle"]["reason"] = "revised_design_published"


def fresh_current_design_passes(state: dict[str, Any], review_kind: str) -> list[dict[str, str]]:
    """Return PASS review/attempt pairs that prove current registered ingestion."""
    publication = current_design_publication(state)
    pairs: list[dict[str, str]] = []
    for review in state.get("reviews", []):
        if (
            review.get("review_kind") != review_kind
            or review.get("verdict") != "PASS"
            or review.get("subject_fingerprint") != publication.get("publication_hash")
            or review.get("intent_revision") != publication.get("intent_revision")
            or review.get("target_revision") != publication.get("published_revision")
            or review.get("invalidated_by")
        ):
            continue
        attempts = [
            attempt for attempt in state.get("attempts", [])
            if attempt.get("kind") == "review"
            and attempt.get("mode") == review_kind
            and attempt.get("state") == "RETURNED"
            and attempt.get("review_result") == "PASS"
            and attempt.get("subject_ref") == publication.get("id")
            and attempt.get("subject_fingerprint") == publication.get("publication_hash")
            and attempt.get("subject_revision") == publication.get("published_revision")
            and attempt.get("target_revision") == publication.get("published_revision")
            and attempt.get("intent_revision") == publication.get("intent_revision")
            and attempt.get("return_ref") == review.get("return_ref")
            and attempt.get("packet_hash")
            and attempt.get("lease", {}).get("state") == "released"
            and not attempt.get("invalidated_by")
        ]
        for attempt in attempts:
            pairs.append({"review_id": review["id"], "attempt_id": attempt["id"]})
    return pairs


def _publication_lineage_bindings(record: dict[str, Any]) -> dict[str, Any]:
    revisions = {
        value for value in (record.get("subject_revision"), record.get("target_revision"))
        if value is not None
    }
    return {
        "subject_ref": record.get("subject_ref"),
        "subject_fingerprint": record.get("subject_fingerprint"),
        "revisions": sorted(revisions),
    }


def resolve_review_finding_lineage(state: dict[str, Any], issue: dict[str, Any]) -> dict[str, Any]:
    """Resolve an issue to one publication without using names as evidence."""
    if issue.get("type") != "review_finding":
        return {"status": "not_review_finding", "reason": "issue type is not review_finding"}
    finding = next(
        (item for item in state.get("findings", []) if item.get("id") == issue.get("finding_ref")),
        None,
    )
    if finding is None:
        return {"status": "unresolved", "reason": "missing finding_ref target"}

    source_ids = []
    for source_id in (issue.get("source_ref"), finding.get("source_ref")):
        if source_id and source_id not in source_ids:
            source_ids.append(source_id)
    records: list[dict[str, Any]] = []
    source_record_ids: set[str] = set()
    for source_id in source_ids:
        matches = [
            item for collection in ("attempts", "reviews")
            for item in state.get(collection, []) if item.get("id") == source_id
        ]
        if len(matches) != 1:
            reason = "source_ref does not resolve to one attempt/review" if not matches else "source_ref resolves ambiguously"
            return {"status": "unresolved", "reason": reason, "source_ref": source_id}
        records.append(matches[0])
        source_record_ids.add(source_id)

    if not records:
        return {"status": "unresolved", "reason": "finding has no durable attempt/review source"}

    # A return object is the canonical bridge between an attempt and its review.
    return_refs = {item.get("return_ref") for item in records if item.get("return_ref")}
    for collection in ("attempts", "reviews"):
        for item in state.get(collection, []):
            linked_by_return = item.get("return_ref") in return_refs if item.get("return_ref") else False
            linked_by_finding = finding["id"] in item.get("finding_refs", [])
            if linked_by_return or linked_by_finding:
                if item.get("id") not in source_record_ids:
                    records.append(item)
                    source_record_ids.add(item["id"])

    histories = design_publication_history(state)
    candidates = list(histories)
    binding_count = 0
    binding_summary: list[dict[str, Any]] = []
    for record in records:
        bindings = _publication_lineage_bindings(record)
        if len(bindings["revisions"]) > 1:
            return {
                "status": "unresolved",
                "reason": "source record has conflicting subject/target revisions",
                "source_ref": record.get("id"),
            }
        used: dict[str, Any] = {"record_id": record.get("id")}
        if bindings["subject_ref"]:
            candidates = [item for item in candidates if item.get("id") == bindings["subject_ref"]]
            used["subject_ref"] = bindings["subject_ref"]
            binding_count += 1
        if bindings["subject_fingerprint"]:
            candidates = [item for item in candidates if item.get("publication_hash") == bindings["subject_fingerprint"]]
            used["subject_fingerprint"] = bindings["subject_fingerprint"]
            binding_count += 1
        if bindings["revisions"]:
            revision = bindings["revisions"][0]
            candidates = [item for item in candidates if item.get("published_revision") == revision]
            used["subject_revision"] = revision
            binding_count += 1
        if len(used) > 1:
            binding_summary.append(used)

    if binding_count == 0:
        return {"status": "unresolved", "reason": "source records contain no canonical publication bindings"}
    unique = {item.get("id"): item for item in candidates if item.get("id")}
    if not unique:
        return {
            "status": "unresolved",
            "reason": "canonical source bindings match no design publication history record",
            "bindings": binding_summary,
        }
    if len(unique) != 1:
        return {
            "status": "ambiguous",
            "reason": "canonical source bindings match multiple design publications",
            "candidate_publication_ids": sorted(unique),
            "bindings": binding_summary,
        }
    publication = next(iter(unique.values()))
    current = state.get("design_publication", {})
    if publication.get("id") == current.get("id"):
        lineage_status = "current"
        reason = "finding is bound to the current design publication"
    elif publication.get("status") in ("SUPERSEDED", "INVALIDATED") or publication.get("superseded_by") or publication.get("invalidated_by"):
        lineage_status = "superseded"
        reason = "finding is bound to a non-current superseded/invalidated publication"
    else:
        lineage_status = "unresolved"
        reason = "matched publication is non-current but lacks supersession/invalidation evidence"
    return {
        "status": lineage_status,
        "reason": reason,
        "publication_id": publication.get("id"),
        "publication_fingerprint": publication.get("publication_hash"),
        "publication_revision": publication.get("published_revision"),
        "finding_id": finding["id"],
        "source_record_ids": sorted(source_record_ids),
        "bindings": binding_summary,
    }


def _append_invalidation(record: dict[str, Any], marker: str) -> None:
    if marker not in record.setdefault("invalidated_by", []):
        record["invalidated_by"].append(marker)


def _apply_review_currentness_resolution(
    state: dict[str, Any], issue: dict[str, Any], resolution: dict[str, Any], marker: str
) -> list[str]:
    """Fence one proven historical closure while retaining every source record."""
    changed: list[str] = []
    ids = {issue["id"], resolution["finding_id"], *resolution["source_record_ids"]}
    source_attempt_ids = {
        item["id"] for item in state.get("attempts", []) if item.get("id") in ids
    }
    for evidence in state.get("evidence", []):
        if evidence.get("subject") in source_attempt_ids:
            ids.add(evidence["id"])
    for collection in ("issues", "findings", "attempts", "reviews", "evidence"):
        for record in state.get(collection, []):
            if record.get("id") in ids and marker not in record.get("invalidated_by", []):
                _append_invalidation(record, marker)
                changed.append(record["id"])
    return sorted(changed)


def cmd_migrate_review_currentness(args: argparse.Namespace) -> dict[str, Any]:
    """Fence provably historical legacy review findings without rewriting them."""
    p = paths(args.control_root, args.run_id)
    with Lock(p["lock"]):
        state, previous_raw = load_mutation_state(p, args.owner_token, args.revision)
        if state["lifecycle"]["control"] in ("ACCEPTED", "FAILED", "CANCELLED"):
            fail("terminal run is immutable; start a successor run")
        admit_event(state, "review.currentness.migrate")
        publication = current_design_publication(state)
        marker = f"review-currentness-{publication['publication_hash']}"
        provenance = state.get("runtime_provenance", {})
        prior = next(
            (item for item in provenance.get("applied_migrations", []) if item.get("id") == marker),
            None,
        )
        if prior is not None:
            report = stored_payload(p, prior.get("object_ref"), "review currentness migration report")
            if sha256_bytes(canonical_bytes(report)) != prior.get("manifest_hash"):
                fail("stored review currentness migration report hash mismatch")
            return {
                "migrated": True,
                "idempotent": True,
                "migration_id": marker,
                "revision": state["revision"],
                "report": report,
            }

        passes = {
            kind: fresh_current_design_passes(state, kind)
            for kind in ("coverage", "plan")
        }
        missing_passes = [kind for kind, pairs in passes.items() if not pairs]
        if missing_passes:
            fail(
                "review currentness migration requires fresh registered and ingested current PASS: "
                + ", ".join(missing_passes)
            )

        next_state = copy.deepcopy(state)
        outcomes: list[dict[str, Any]] = []
        changed_ids: set[str] = set()
        active_findings = [
            item for item in next_state.get("issues", [])
            if item.get("type") == "review_finding"
            and item.get("impact") == "blocking"
            and not item.get("invalidated_by")
        ]
        for issue in active_findings:
            resolution = resolve_review_finding_lineage(next_state, issue)
            outcome = {"issue_id": issue["id"], **resolution}
            if resolution.get("status") == "superseded":
                changed = _apply_review_currentness_resolution(next_state, issue, resolution, marker)
                changed_ids.update(changed)
                outcome["action"] = "invalidated_as_historical"
                outcome["changed_record_ids"] = changed
            else:
                outcome["action"] = "preserved_as_current_blocker"
            outcomes.append(outcome)

        if not changed_ids:
            return {
                "migrated": False,
                "idempotent": True,
                "no_effect": True,
                "migration_id": marker,
                "revision": state["revision"],
                "outcomes": outcomes,
            }

        current_blocker_ids = [
            item["id"] for item in next_state.get("issues", [])
            if item.get("impact") == "blocking" and not item.get("invalidated_by")
        ]
        next_state["lifecycle"]["issue_refs"] = [
            ref for ref in next_state["lifecycle"].get("issue_refs", []) if ref in current_blocker_ids
        ]
        if next_state["lifecycle"].get("control") == "BLOCKED" and not current_blocker_ids:
            next_state["lifecycle"]["control"] = "ACTIVE"
            next_state["lifecycle"]["reason"] = "review_currentness_migrated"
            next_state["lifecycle"]["next_action"] = {
                "kind": "advance_g2_g3",
                "subject_refs": [publication["id"]],
                "preconditions": ["current coverage PASS", "current plan PASS", "no current blocking issues"],
                "read_refs": ["phases/design.md", "references/ledger.md"],
            }

        report = {
            "kind": "review_currentness_migration",
            "migration_id": marker,
            "run_id": state["run_id"],
            "source_revision": state["revision"],
            "applied_revision": state["revision"] + 1,
            "current_publication": {
                "id": publication["id"],
                "publication_hash": publication["publication_hash"],
                "published_revision": publication["published_revision"],
            },
            "fresh_passes": passes,
            "outcomes": outcomes,
            "changed_record_ids": sorted(changed_ids),
            "remaining_current_blocker_ids": current_blocker_ids,
        }
        report_raw = canonical_bytes(report)
        report_hash = sha256_bytes(report_raw)
        runtime = ensure_runtime_provenance(next_state)
        runtime["applied_migrations"].append({
            "id": marker,
            "helper_version": SKILL_VERSION,
            "applied_revision": state["revision"] + 1,
            "manifest_hash": report_hash,
            "object_ref": f"objects/{report_hash}",
        })
        usage = next_state.setdefault("usage", default_usage())
        usage.setdefault("counters", zero_usage())
        usage.setdefault("trace", [])
        usage.setdefault("shared_setup", zero_usage())
        usage.setdefault("gate_costs", {f"G{i}": zero_usage() for i in range(7)})
        delta = {field: 0 for field in USAGE_FIELDS}
        delta["helper_calls"] = 1
        delta["internal_publications"] = 1
        add_usage(usage["counters"], delta)
        usage["trace"].append({
            "id": f"trace-{state['revision'] + 1}-helper",
            "kind": "helper_publication",
            "actor": "ledger-helper",
            "subject_ref": marker,
            "delta": delta,
            "evidence_ref": f"objects/{report_hash}",
            "recorded_at": now(),
        })
        next_state["revision"] = state["revision"] + 1
        next_state["previous_publication_hash"] = sha256_bytes(previous_raw)
        next_state["updated_at"] = now()
        validate_ledger(next_state, verify_files=False)
        object_store(p, report_raw)
        publish(p, next_state, previous_raw, "review-currentness-migration")
        return {
            "migrated": True,
            "idempotent": False,
            "migration_id": marker,
            "revision": next_state["revision"],
            "report_hash": report_hash,
            "report": report,
        }


def design_review_pass(state: dict[str, Any], review_kind: str) -> bool:
    publication = current_design_publication(state)
    return any(
        review.get("review_kind") == review_kind
        and review.get("verdict") == "PASS"
        and review.get("subject_fingerprint") == publication.get("publication_hash")
        and review.get("intent_revision") == publication.get("intent_revision")
        and review.get("target_revision") == publication.get("published_revision")
        and not review.get("invalidated_by")
        for review in state.get("reviews", [])
    )


def require_design_review_stopped(p: dict[str, Path], state: dict[str, Any], review_kind: str) -> None:
    publication = current_design_publication(state)
    for review in state.get("reviews", []):
        if (
            review.get("review_kind") == review_kind
            and review.get("verdict") == "PASS"
            and review.get("subject_fingerprint") == publication.get("publication_hash")
            and review.get("intent_revision") == publication.get("intent_revision")
            and review.get("target_revision") == publication.get("published_revision")
            and not review.get("invalidated_by")
        ):
            attempt_id = review.get("attempt_ref")
            if attempt_id:
                require_runtime_stopped(p, attempt_by_id(state, attempt_id), f"{review_kind} review qualification")


def cmd_publish_design_bundle(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    bundle_path = Path(args.bundle).expanduser().resolve()
    bundle = read_json(bundle_path, "design bundle")
    root = schema()
    validate(bundle, root["$defs"]["design_bundle"], root, "$.design_bundle")
    validate_design_bundle(bundle)
    bundle_hash = sha256_bytes(canonical_bytes(bundle))
    source_bytes = {document["id"]: design_bundle_source(document)[1] for document in bundle["documents"]}
    started = time.monotonic()

    with Lock(p["lock"]):
        state, previous_raw = load_mutation_state(p, args.owner_token)
        if state["owner"]["token"] != args.owner_token:
            fail("owner token mismatch; stale orchestrator is fenced")
        existing = state.get("design_publication")
        # A response can be lost after the ledger commit.  If the exact
        # immutable publication is already current, adopting it is safe even
        # when the caller retries with the pre-commit revision.
        if existing and existing.get("status") == "PUBLISHED" and existing.get("publication_hash") == bundle_hash and existing.get("id") == bundle["bundle_id"]:
            return {"published": True, "idempotent": True, "bundle_id": bundle["bundle_id"], "publication_hash": bundle_hash, "revision": state["revision"], "next_action": state["lifecycle"]["next_action"]}
        if state["revision"] != args.revision:
            fail(f"revision mismatch: expected {args.revision}, current {state['revision']}")
        if state["lifecycle"]["control"] in ("ACCEPTED", "FAILED", "CANCELLED"):
            fail("terminal run is immutable; start a successor run")
        admit_event(state, "design.publish")
        if state["lifecycle"]["phase"] != "DESIGN":
            fail("design bundle publication requires a G1-complete DESIGN phase")
        if state.get("candidate_model_version") != "1.1" and bundle.get("tickets"):
            fail("legacy state without the Phase B candidate model cannot publish worker tickets; use an explicit compatible migration")
        binding = current_intent_binding(state)
        if bundle["epoch"] != state["owner"]["epoch"]:
            fail("design bundle epoch does not match current owner")
        if (bundle["intent_revision"], bundle["intent_document_ref"], bundle["intent_document_hash"]) != (binding["revision"], binding["document_ref"], binding["document_hash"]):
            fail("design bundle is bound to a stale intent")
        if existing:
            if state["lifecycle"]["phase"] != "DESIGN":
                fail("design republish is only legal during DESIGN")
            if not design_publication_requires_revision(state, existing):
                fail("conflicting design bundle is already published; current publication does not have an eligible BLOCK/UNVERIFIABLE repair transition")
            active = active_publication_leases(state)
            if active:
                fail(f"design republish requires stopped writers/reviewers and released leases: {', '.join(active)}")
            if bundle["version"] == existing.get("version"):
                fail("revised design publication requires a new bundle version")

        collections = {collection: {item.get("id"): item for item in state.get(collection, [])} for collection in ("documents", "contracts", "tickets", "routes")}
        occupied = {item.get("id") for collection in state.values() if isinstance(collection, list) for item in collection if isinstance(item, dict) and item.get("id")}
        if bundle["bundle_id"] in occupied:
            fail("design bundle ID conflicts with an existing immutable ID")
        if state.get("design_publication") and state["design_publication"].get("id") == bundle["bundle_id"]:
            fail("design bundle ID was already used by a prior publication")
        for collection_name in ("documents", "contracts", "tickets", "routes"):
            for record in bundle[collection_name]:
                normalized_record = copy.deepcopy(record)
                if collection_name == "tickets" and state.get("candidate_model_version") == "1.1":
                    normalized_record.setdefault("current_attempt", None)
                    normalized_record.setdefault("current_worker_attempt", None)
                    normalized_record.setdefault("last_worker_attempt", None)
                    normalized_record.setdefault("current_candidate", None)
                existing_record = collections[collection_name].get(record["id"])
                if record["id"] in occupied and (existing_record is None or existing_record != normalized_record and collection_name != "documents"):
                    fail(f"design bundle ID conflicts with an existing immutable ID: {record['id']}")
        next_state = copy.deepcopy(state)
        prior_publication = copy.deepcopy(existing) if existing else None
        if prior_publication:
            supersede_design_publication(next_state, prior_publication, bundle["bundle_id"])
        next_state.setdefault("documents", [])
        for document in bundle["documents"]:
            canonical = {"id": document["id"], "version": document["version"], "path": str(canonical_document_path(p, document["id"], document["version"])), "hash": document["hash"], "kind": document["kind"], "section_anchors": document.get("section_anchors", [])}
            existing_document = collections["documents"].get(document["id"])
            if existing_document is not None:
                if existing_document != canonical:
                    fail(f"conflicting canonical document: {document['id']}")
                continue
            next_state["documents"].append(canonical)
        for collection_name in ("contracts", "tickets", "routes"):
            for record in bundle[collection_name]:
                canonical_record = copy.deepcopy(record)
                if collection_name == "tickets" and next_state.get("candidate_model_version") == "1.1":
                    canonical_record.setdefault("current_attempt", None)
                    canonical_record.setdefault("current_worker_attempt", None)
                    canonical_record.setdefault("last_worker_attempt", None)
                    canonical_record.setdefault("current_candidate", None)
                existing_record = collections[collection_name].get(record["id"])
                if existing_record is not None:
                    if existing_record != canonical_record:
                        fail(f"conflicting canonical {collection_name[:-1]}: {record['id']}")
                    continue
                next_state.setdefault(collection_name, []).append(canonical_record)
        known_criteria = {item["id"] for item in next_state.get("criteria", [])}
        known_contracts = {item["id"] for item in next_state.get("contracts", [])}
        known_tickets = {item["id"] for item in next_state.get("tickets", [])}
        validate_ticket_contract_bindings(next_state.get("contracts", []), bundle["tickets"], "design bundle")
        for ticket in bundle["tickets"]:
            if not set(ticket.get("criterion_refs", [])).issubset(known_criteria):
                fail(f"design ticket references an unknown criterion: {ticket['id']}")
            if not set(ticket.get("contract_refs", [])).issubset(known_contracts):
                fail(f"design ticket references an unknown contract: {ticket['id']}")
            if not set(ticket.get("dependency_refs", [])).issubset(known_tickets):
                fail(f"design ticket references an unknown dependency: {ticket['id']}")

        document_refs = [item["id"] for item in bundle["documents"]]
        active_requirement_refs = [item["id"] for item in next_state.get("requirements", []) if item.get("status") == "active"]
        active_criterion_refs = [item["id"] for item in next_state.get("criteria", []) if item.get("status") == "active"]
        requirements_publication = next((item for item in reversed(next_state.get("requirements_publications", [])) if item.get("status") == "PUBLISHED" and item.get("intent_revision") == binding["revision"] and item.get("intent_document_hash") == binding["document_hash"]), None)
        new_publication = {
            "id": bundle["bundle_id"], "version": bundle["version"], "status": "PUBLISHED", "owner_epoch": state["owner"]["epoch"],
            "intent_revision": binding["revision"], "intent_document_ref": binding["document_ref"], "intent_document_hash": binding["document_hash"],
            "publication_hash": bundle_hash, "bundle_ref": f"objects/{bundle_hash}", "published_revision": state["revision"] + 1,
            "document_refs": document_refs, "requirement_refs": active_requirement_refs, "criterion_refs": active_criterion_refs,
            "requirements_publication_ref": requirements_publication.get("id") if requirements_publication else None,
            "contract_refs": [item["id"] for item in bundle["contracts"]], "ticket_refs": [item["id"] for item in bundle["tickets"]], "route_refs": [item["id"] for item in bundle["routes"]],
        }
        if prior_publication:
            new_publication["supersedes"] = [prior_publication["id"]]
        next_state["design_publication"] = new_publication
        next_state.setdefault("design_publication_history", []).append(copy.deepcopy(new_publication))
        if state["lifecycle"]["control"] == "BLOCKED" and state["lifecycle"].get("reason") in ("missing_design_publication", "design_publication_required", "design_artifacts_unpublished", "publication_gap"):
            publication_blockers = set(state["lifecycle"].get("issue_refs", []))
            unrelated_blockers = [issue for issue in state.get("issues", []) if issue.get("id") in publication_blockers and issue.get("type") not in ("design_publication_gap", "missing_design_publication")]
            if not unrelated_blockers:
                for issue in next_state.get("issues", []):
                    if issue.get("id") in publication_blockers:
                        issue["impact"] = "advisory"
                        issue["disposition"] = "resolved by design publication"
                next_state["lifecycle"]["issue_refs"] = []
                next_state["lifecycle"]["control"] = "ACTIVE"
        next_state["lifecycle"]["next_action"] = {"kind": "prepare_g2_coverage_review", "subject_refs": [bundle["bundle_id"], *document_refs], "preconditions": ["published design bundle is current", "fresh coverage reviewer attempt"], "read_refs": ["phases/design.md", "contracts/reviewer.md", "references/ledger.md"]}
        destinations: list[tuple[Path, bytes, str]] = []
        for document in bundle["documents"]:
            destination = canonical_document_path(p, document["id"], document["version"])
            if destination.exists():
                regular_non_symlink(destination)
                if destination.read_bytes() != source_bytes[document["id"]]:
                    fail(f"canonical design document destination already exists with different bytes: {document['id']}")
            destinations.append((destination, source_bytes[document["id"]], document["id"]))
        usage = next_state.setdefault("usage", default_usage())
        usage.setdefault("counters", zero_usage()); usage.setdefault("trace", []); usage.setdefault("shared_setup", zero_usage()); usage.setdefault("gate_costs", {f"G{i}": zero_usage() for i in range(7)})
        delta = {field: 0 for field in USAGE_FIELDS}; delta["helper_calls"] = 1; delta["internal_publications"] = 1; delta["wall_time_ms"] = max(0, int((time.monotonic() - started) * 1000))
        add_usage(usage["counters"], delta)
        usage["trace"].append({"id": f"trace-{state['revision'] + 1}-helper", "kind": "helper_publication", "actor": "ledger-helper", "subject_ref": bundle["bundle_id"], "delta": delta, "evidence_ref": None, "recorded_at": now()})
        next_state["revision"] = state["revision"] + 1
        next_state["previous_publication_hash"] = sha256_bytes(previous_raw)
        next_state["updated_at"] = now()
        validate_ledger(next_state, verify_files=False)
        object_store(p, canonical_bytes(bundle))
        for destination, raw, _document_id in destinations:
            if not destination.exists():
                atomic_create(destination, raw)
        validate_ledger(next_state)
        publish(p, next_state, previous_raw, "design-publication")
    return {"published": True, "idempotent": False, "bundle_id": bundle["bundle_id"], "publication_hash": bundle_hash, "revision": next_state["revision"], "next_action": next_state["lifecycle"]["next_action"]}


def cmd_amend(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    raw = intent_source_bytes(args.intent_file)
    digest = sha256_bytes(raw)
    doc_path = canonical_document_path(p, args.doc_id, args.doc_version)
    doc_id = args.doc_id

    def reconcile_retry(state: dict[str, Any]) -> dict[str, Any] | None:
        """Recognize only this exact amendment after a committed publication."""
        if state.get("revision") != args.revision + 1:
            return None
        if not p["prev"].exists() or sha256_bytes(p["prev"].read_bytes()) != state.get("previous_publication_hash"):
            return None
        invalidation = next((item for item in state.get("invalidations", []) if item.get("amendment_ref") == args.amendment_id), None)
        document = next((item for item in state.get("documents", []) if item.get("id") == doc_id and item.get("version") == args.doc_version), None)
        intent = state.get("intent", {})
        if (
            invalidation is None
            or invalidation.get("intent_revision") != args.intent_revision
            or document is None
            or document.get("path") != str(doc_path)
            or document.get("hash") != digest
            or intent.get("current_revision") != args.intent_revision
            or intent.get("document_ref") != doc_id
            or intent.get("document_hash") != digest
            or args.amendment_id not in intent.get("approved_amendments", [])
        ):
            return None
        regular_non_symlink(doc_path)
        if doc_path.read_bytes() != raw:
            return None
        # The ledger is authoritative after replacement. Complete the missing
        # deterministic snapshot before acknowledging this exact retry.
        write_snapshot(p, state, "amendment")
        prune_snapshots(p)
        return {
            "amended": True,
            "idempotent": True,
            "document_hash": digest,
            "revision": state["revision"],
            "next_action": state["lifecycle"]["next_action"],
        }

    def change(state: dict[str, Any]) -> None:
        admit_event(state, "intent.amend")
        if not args.authority_ref:
            fail("amendment requires explicit user authority reference")
        old_binding = current_intent_binding(state)
        documents = state.setdefault("documents", [])
        if any(d.get("id") == doc_id and d.get("version") == args.doc_version for d in documents):
            fail("document revision already exists")
        if any(item.get("amendment_ref") == args.amendment_id for item in state.get("invalidations", [])):
            fail("amendment ID already exists")
        documents.append({"id": doc_id, "version": args.doc_version, "path": str(doc_path), "hash": digest, "kind": "intent", "section_anchors": []})

        collections = ("documents", "requirements_publications", "requirements", "criteria", "contracts", "decisions", "tickets", "attempts", "issues", "findings", "reviews", "acceptance", "operations", "capabilities", "routes", "evidence")
        consumer_refs: list[str] = []
        for collection in collections:
            for item in state.get(collection, []):
                if collection == "documents" and item.get("id") == doc_id:
                    continue
                if item.get("id"):
                    consumer_refs.append(item["id"])
                    if "invalidated_by" in item or collection in {"documents", "requirements_publications", "requirements", "criteria", "contracts", "decisions", "tickets", "attempts", "issues", "findings", "reviews", "acceptance", "operations", "capabilities", "routes", "evidence"}:
                        item.setdefault("invalidated_by", []).append(args.amendment_id)
                    if collection == "requirements_publications":
                        item["status"] = "INVALIDATED"
        if state.get("design_publication"):
            current_publication = state["design_publication"]
            history = state.setdefault("design_publication_history", [])
            if not any(item.get("id") == current_publication.get("id") for item in history):
                history.append(copy.deepcopy(current_publication))
            for publication in history:
                if publication.get("id") == current_publication.get("id"):
                    publication.setdefault("invalidated_by", []).append(args.amendment_id)
                    publication["status"] = "INVALIDATED"
            current_publication.setdefault("invalidated_by", []).append(args.amendment_id)
            current_publication["status"] = "INVALIDATED"
            consumer_refs.append(current_publication["id"])
        state.setdefault("invalidations", []).append({"id": f"invalidation-{args.amendment_id}", "amendment_ref": args.amendment_id, "intent_revision": args.intent_revision, "previous_intent_revision": old_binding["revision"], "previous_document_ref": old_binding["document_ref"], "previous_document_hash": old_binding["document_hash"], "affected_refs": [old_binding["document_ref"], doc_id], "consumer_refs": sorted(set(consumer_refs)), "recorded_at": now()})
        state["intent"] = {"current_revision": args.intent_revision, "document_ref": doc_id, "document_hash": digest, "approved_amendments": [*state.get("intent", {}).get("approved_amendments", []), args.amendment_id], "acceptance_policy": state.get("intent", {}).get("acceptance_policy", "automatic"), "checkpoint_policy": state.get("intent", {}).get("checkpoint_policy", "gate"), "prior_accepted_refs": state.get("intent", {}).get("prior_accepted_refs", [])}
        for ticket in state.get("tickets", []):
            if ticket.get("state") not in ("CANCELLED", "STALE"):
                ticket["state"] = "STALE"
            ticket.setdefault("intent_revision", old_binding["revision"])
        for attempt in state.get("attempts", []):
            if attempt.get("state") in ("PREPARED", "DISPATCHED"):
                attempt["lease"]["state"] = "quarantined"
            attempt.setdefault("intent_revision", old_binding["revision"])
        state["lifecycle"]["phase"] = "INTENT"
        state["lifecycle"]["control"] = "ACTIVE"
        state["lifecycle"]["reason"] = "user_amendment"
        state["lifecycle"]["next_action"] = {"kind": "g1_recheck", "subject_refs": [args.amendment_id], "preconditions": ["affected work quiesced", "current intent hash verified"], "read_refs": ["phases/intent.md", "references/ledger.md"]}
        active_plan = _ACTIVE_WRITE_PLAN.get()
        if active_plan is None:
            fail("canonical amendment write requires a locked immutable write plan")
        active_plan.add(doc_path, raw, "canonical")

    try:
        result = transaction(p, args.owner_token, args.revision, change, "amendment", retry_reconcile=reconcile_retry)
    except IdempotentResult as prior:
        return prior.result
    return {"amended": True, "document_hash": digest, "revision": result["revision"], "next_action": result["lifecycle"]["next_action"]}


def cmd_gate(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    def change(state: dict[str, Any]) -> None:
        phase = args.phase or state["lifecycle"]["phase"]
        control = args.control or state["lifecycle"]["control"]
        if phase not in PHASES or control not in CONTROLS:
            fail("invalid phase/control")
        current_phase = state["lifecycle"]["phase"]
        current_control = state["lifecycle"]["control"]
        if current_control in ("ACCEPTED", "FAILED", "CANCELLED"):
            fail("terminal run is immutable; start a successor run")
        if control == "CANCELLED":
            fail("direct CANCELLED bypass is forbidden; enter QUIESCING and use cancel --finalize")
        if control == "PAUSED" and current_control != "QUIESCING":
            fail("PAUSED requires a prior QUIESCING transition")
        gate_event = "run.resume" if current_control == "PAUSED" else "lifecycle.advance"
        admit_event(state, gate_event)
        validate_control_transition(current_control, control)
        gate_id = getattr(args, "gate_id", None)
        if gate_id is not None and gate_id not in {f"G{index}" for index in range(7)}:
            fail("gate ID must be one of G0 through G6")
        expected_gate = None
        if control == "ACTIVE" and current_phase == "DESIGN" and phase == "PLAN":
            # G3 identifies the DESIGN -> PLAN lifecycle gate even when the run
            # is resuming from BLOCKED/PAUSED/RECOVERING; same-phase recovery is
            # not a gate and does not infer G2.
            expected_gate = "G3"
        elif current_control == "ACTIVE" and control == "ACTIVE":
            expected_gate = {
                ("DESIGN", "DESIGN"): "G2",
                ("EXECUTE", "VERIFY"): "G4",
                ("VERIFY", "ACCEPT"): "G5",
            }.get((current_phase, phase))
        if control == "ACCEPTED" and phase == "ACCEPT":
            expected_gate = "G6"
        if gate_id is not None and gate_id != expected_gate:
            fail(f"gate ID {gate_id} does not match lifecycle gate {expected_gate or 'none'}")
        if control == "QUIESCING" and current_control not in ("ACTIVE", "BLOCKED", "RECOVERING"):
            fail(f"cannot enter QUIESCING from {current_control}")
        if control == "PAUSED":
            if current_control != "QUIESCING":
                fail("PAUSED requires a prior QUIESCING transition")
            active_attempts = [
                attempt for attempt in state.get("attempts", [])
                if attempt.get("state") in ("PREPARED", "DISPATCHED")
            ]
            active_leases = [
                attempt for attempt in state.get("attempts", [])
                if attempt.get("lease", {}).get("state") in ("active", "quarantined")
            ]
            unresolved_effects = [
                operation for operation in state.get("operations", [])
                if effect_is_unresolved(operation)
            ]
            if active_attempts or active_leases or unresolved_effects:
                fail("PAUSED requires stopped writers, released leases, and reconciled effects")
        if current_control == "RECOVERING" and control == "ACTIVE":
            active_attempts = [
                attempt for attempt in state.get("attempts", [])
                if attempt.get("state") in ("PREPARED", "DISPATCHED")
            ]
            active_leases = [
                attempt for attempt in state.get("attempts", [])
                if attempt.get("lease", {}).get("state") in ("active", "quarantined")
            ]
            unresolved_effects = [
                operation for operation in state.get("operations", [])
                if effect_is_unresolved(operation)
            ]
            if active_attempts or active_leases or unresolved_effects:
                fail("RECOVERING -> ACTIVE requires no in-flight attempts, active/quarantined leases, or unresolved effects")
        blockers = [item for item in state.get("issues", []) if item.get("impact") == "blocking" and not item.get("invalidated_by")]
        g2_claim = control == "ACTIVE" and gate_id == "G2"
        g3_claim = control == "ACTIVE" and gate_id == "G3"
        if state.get("intent") and (g2_claim or g3_claim):
            current_publication = current_design_publication(state)
            current_design_tickets = [
                item for item in state.get("tickets", [])
                if item.get("id") in set(current_publication.get("ticket_refs", []))
            ]
            validate_effective_ticket_contract_bindings(
                state, current_design_tickets, f"{gate_id} design publication",
                require_availability=True, allow_planned_producers=True,
            )
            require_design_review_stopped(p, state, "coverage")
            if not design_review_pass(state, "coverage"):
                fail("G2 cannot pass without a PASS coverage review of the current published design bundle")
            if g3_claim:
                require_design_review_stopped(p, state, "plan")
                if not design_review_pass(state, "plan"):
                    fail("G3 cannot pass without a PASS plan review of the current published design bundle")
            if blockers:
                fail("a current blocking issue prevents G2/G3 advancement")
        if (
            state.get("candidate_model_version") == "1.1"
            and control == "ACTIVE"
            and expected_gate in ("G2", "G3")
            and gate_id is None
        ):
            fail(f"{expected_gate} advancement requires an explicit --gate-id {expected_gate}")
        if current_control == "BLOCKED" and control == "ACTIVE":
            open_obligations = [
                item for item in finding_obligation_projection(state)["obligations"]
                if item.get("status") != "closed"
            ]
            if blockers or open_obligations:
                fail("BLOCKED -> ACTIVE requires no active blocking issues or unresolved finding obligations")
        current_index = PHASES.index(current_phase)
        requested_index = PHASES.index(phase)
        design_repair_return = (
            phase == "DESIGN"
            and current_phase == "PLAN"
            and current_control == "BLOCKED"
            and isinstance(state.get("design_publication"), dict)
            and design_publication_requires_revision(state, state["design_publication"])
        )
        if design_repair_return and active_publication_leases(state):
            fail("DESIGN repair transition requires stopped writers/reviewers and released leases")
        execution_repair_return = phase == "EXECUTE" and current_phase in ("VERIFY", "ACCEPT") and current_control == "BLOCKED"
        contract_repair_return = phase == "DESIGN" and current_phase in ("EXECUTE", "VERIFY", "ACCEPT") and current_control == "BLOCKED"
        intent_repair_return = phase == "INTENT" and current_phase in ("DESIGN", "PLAN", "EXECUTE", "VERIFY", "ACCEPT") and current_control == "BLOCKED"
        if phase not in PHASE_TRANSITION_TABLE.get(current_phase, frozenset()) and not (design_repair_return or execution_repair_return or contract_repair_return or intent_repair_return):
            fail(f"illegal phase jump: {current_phase} -> {phase}")
        if current_phase == "PLAN" and phase == "EXECUTE":
            publication = current_design_publication(state)
            current_design_tickets = [
                item for item in state.get("tickets", [])
                if item.get("id") in set(publication.get("ticket_refs", []))
            ]
            validate_effective_ticket_contract_bindings(
                state, current_design_tickets, "execution entry",
                require_availability=True, allow_planned_producers=True,
            )
            require_design_review_stopped(p, state, "coverage")
            require_design_review_stopped(p, state, "plan")
            if not design_review_pass(state, "coverage") or not design_review_pass(state, "plan"):
                fail("execution requires current G2 coverage PASS and G3 plan PASS")
            if any(ticket.get("id") in publication.get("ticket_refs", []) and ticket.get("state") not in ("PLANNED", "READY") for ticket in state.get("tickets", [])):
                fail("execution entry requires current design tickets to be PLANNED/READY")
            if blockers:
                fail("execution entry is blocked by current issues")
        if current_phase == "EXECUTE" and phase == "VERIFY":
            publication = current_design_publication(state)
            current_tickets = [ticket for ticket in state.get("tickets", []) if ticket.get("id") in publication.get("ticket_refs", [])]
            if not current_tickets or any(ticket.get("state") != "INTEGRATED" for ticket in current_tickets):
                fail("G4 requires every current publication ticket to be reviewed and INTEGRATED")
            if active_publication_leases(state) or any(effect_is_unresolved(op) for op in state.get("operations", [])):
                fail("G4 requires released leases and reconciled effects")
            if blockers:
                fail("G4 is blocked by current issues")
        if control == "FAILED":
            if current_control != "QUIESCING" or active_publication_leases(state) or any(effect_is_unresolved(op) for op in state.get("operations", [])):
                fail("FAILED requires QUIESCING with stopped attempts and reconciled effects")
        if control == "ACCEPTED":
            if current_phase != "ACCEPT" or phase != "ACCEPT":
                fail("G6 terminal acceptance requires ACCEPT phase")
            latest = state.get("acceptance", [])[-1] if state.get("acceptance") else None
            binding = current_intent_binding(state)
            if not latest or latest.get("verdict") != "PASS" or latest.get("intent_revision") != binding["revision"] or latest.get("invalidated_by"):
                fail("G6 cannot mark ACCEPTED without a fresh current-intent G5 PASS")
            if (
                state.get("review_model_version") == "1.1"
                and (latest.get("purpose") == "final_g5" or latest.get("qualification_ref") is not None)
            ):
                final_qualifications = [
                    item for item in state.get("review_qualifications", [])
                    if item.get("result") == "PASS"
                    and item.get("required_purposes") == ["final_g5"]
                    and item.get("id") == latest.get("qualification_ref")
                    and item.get("intent_revision") == binding["revision"]
                    and item.get("subject_fingerprint") == latest.get("candidate_fingerprint")
                    and latest.get("return_ref") in item.get("accepted_return_refs", [])
                ]
                if not final_qualifications:
                    fail("G6 requires the immutable fresh final-G5 qualification for this exact acceptance return")
                if any(item.get("state") == "OPEN" for item in state.get("repair_waves", [])):
                    fail("G6 requires every final-G5 repair wave to be closed")
            open_obligations = [
                item for item in finding_obligation_projection(state)["obligations"]
                if item.get("status") != "closed"
            ]
            if blockers or open_obligations or active_publication_leases(state) or any(effect_is_unresolved(op) for op in state.get("operations", [])):
                fail("G6 requires no blockers, active/quarantined leases, or unresolved effects")
            if state.get("candidate_model_version") == "1.1" and gate_id != "G6":
                fail("G6 acceptance requires an explicit --gate-id G6")
        state["lifecycle"]["phase"] = phase
        state["lifecycle"]["control"] = control
        state["lifecycle"]["reason"] = args.reason
        state["lifecycle"]["next_action"] = {"kind": args.next_action, "subject_refs": [x for x in args.subject_refs.split(",") if x], "preconditions": [x for x in args.preconditions.split("|") if x], "read_refs": [x for x in args.read_refs.split(",") if x]}
    result = transaction(p, args.owner_token, args.revision, change, "gate")
    return {"published": True, "revision": result["revision"], "phase": result["lifecycle"]["phase"], "control": result["lifecycle"]["control"]}


def cmd_cancel(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    if not args.finalize:
        def request(state: dict[str, Any]) -> None:
            admit_event(state, "run.cancel.request")
            if state["lifecycle"]["control"] in ("ACCEPTED", "FAILED", "CANCELLED"):
                fail("terminal run is immutable; start a successor run")
            state["lifecycle"]["control"] = "QUIESCING"
            state["lifecycle"]["reason"] = args.reason
            state["lifecycle"]["stop_target"] = args.stop_target
            state["lifecycle"]["next_action"] = {"kind": "stop_reconcile_then_cancel", "subject_refs": [], "preconditions": ["all known writers stopped", "leases and unresolved effects finalized or abandoned"], "read_refs": ["phases/recover.md", "references/ledger.md"]}
        result = transaction(p, args.owner_token, args.revision, request, "cancel-quiescing")
        return {"quiescing": True, "revision": result["revision"], "control": "QUIESCING"}
    evidence = read_json(Path(args.stop_evidence).expanduser().resolve(), "cancellation stop evidence")
    if evidence.get("status") != "PASS" or evidence.get("writers_stopped") is not True or evidence.get("reconciled") is not True:
        fail("cancellation finalization requires PASS stop/reconcile evidence")
    def finalize(state: dict[str, Any]) -> None:
        admit_event(state, "run.cancel.finalize")
        if state["lifecycle"]["control"] != "QUIESCING":
            fail("cancellation finalization requires QUIESCING")
        if any(effect_is_unresolved(op) for op in state.get("operations", [])):
            fail("cancellation requires all unresolved effects finalized or abandoned")
        for attempt in state.get("attempts", []):
            if attempt.get("lease", {}).get("state") in ("active", "quarantined"):
                require_runtime_stopped(p, attempt, "run cancellation lease release")
            if attempt.get("state") in ("PREPARED", "DISPATCHED"):
                attempt["state"] = "INTERRUPTED"
            if attempt.get("lease", {}).get("state") in ("active", "quarantined"):
                attempt["lease"]["state"] = "released"
        for ticket in state.get("tickets", []):
            if ticket.get("state") not in ("INTEGRATED", "CANCELLED"):
                ticket["state"] = "CANCELLED"
        state["lifecycle"]["control"] = "CANCELLED"
        state["lifecycle"]["reason"] = args.reason
        state["lifecycle"]["next_action"] = {"kind": "terminal_cancelled", "subject_refs": [], "preconditions": [], "read_refs": ["phases/recover.md"]}
    result = transaction(p, args.owner_token, args.revision, finalize, "cancel-terminal")
    return {"cancelled": True, "revision": result["revision"], "control": "CANCELLED"}


def cmd_recover(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    with Lock(p["lock"]):
        try:
            state, previous_raw = load_state(p)
            recovered_from = None
        except LedgerError as exc:
            candidates = recovery_candidates(p, args.run_id)
            if not candidates:
                fail(f"current ledger is corrupt and no verified previous/snapshot exists: {exc}")
            state, previous_raw, source = candidates[0]
            recovered_from = str(source)
        if state["owner"]["token"] != args.owner_token:
            fail("owner token mismatch; stale orchestrator is fenced")
        admit_event(state, "run.recover")
        if not args.takeover and args.revision not in (state["revision"], state["revision"] + 1):
            fail(f"recovery revision does not match verified checkpoint: {args.revision}")
        require_mutation_eligible(state)
        if args.takeover:
            if not args.new_owner_token:
                fail("takeover requires a new owner token")
            state["owner"]["epoch"] += 1
            state["owner"]["token"] = args.new_owner_token
            state["owner"]["attestation_ref"] = args.attestation_ref
            for attempt in state.get("attempts", []):
                if attempt.get("state") in ("PREPARED", "DISPATCHED"):
                    attempt["lease"]["state"] = "quarantined"
        state["lifecycle"]["control"] = "RECOVERING"
        state["lifecycle"]["reason"] = args.reason
        state["lifecycle"]["next_action"] = {"kind": "reconcile_actual_state", "subject_refs": [], "preconditions": ["writer stop/reuse guard", "Git/effect reconciliation"], "read_refs": ["phases/recover.md", "references/ledger.md"]}
        state["revision"] = state["revision"] + 1
        state["previous_publication_hash"] = sha256_bytes(previous_raw)
        state["updated_at"] = now()
        publish(p, state, previous_raw, "recovery")
        return {"recovering": True, "revision": state["revision"], "epoch": state["owner"]["epoch"], "control": "RECOVERING", "recovered_from": recovered_from}

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Codex Autopilot deterministic ledger/contract helper")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init"); init.add_argument("--control-root", required=True); init.add_argument("--repo-root", required=True); init.add_argument("--run-id", required=True); init.add_argument("--owner-token", required=True); init.add_argument("--request", default=None, help="optional natural-language request used to resolve run presets"); init.add_argument("--interaction-mode", choices=["semi", "full"], default=None); init.add_argument("--depth", choices=["normal", "deep"], default=None)
    status = sub.add_parser("status"); status.add_argument("--control-root", required=True); status.add_argument("--run-id", required=True); status.add_argument("--brief", action="store_true")
    diagnose = sub.add_parser("diagnose"); diagnose.add_argument("--control-root", required=True); diagnose.add_argument("--run-id", required=True)
    legacy_diagnose = sub.add_parser("diagnose-legacy", help="read-only structural analysis of a standalone ledger file"); legacy_diagnose.add_argument("--file", required=True)
    assess_bindings = sub.add_parser("assess-legacy-bindings", help="read-only binding compatibility assessment against exact source bytes"); assess_bindings.add_argument("--file", required=True); assess_bindings.add_argument("--manifest", required=True)
    migrate_bindings = sub.add_parser("migrate-legacy-bindings", help="owner-authorized append-only legacy binding normalization"); migrate_bindings.add_argument("--control-root", required=True); migrate_bindings.add_argument("--run-id", required=True); migrate_bindings.add_argument("--owner-token", required=True); migrate_bindings.add_argument("--revision", type=int, required=True); migrate_bindings.add_argument("--manifest", required=True)
    reconcile_bindings = sub.add_parser("reconcile-finding-bindings", help="owner-authorized append-only finding binding recovery"); reconcile_bindings.add_argument("--control-root", required=True); reconcile_bindings.add_argument("--run-id", required=True); reconcile_bindings.add_argument("--owner-token", required=True); reconcile_bindings.add_argument("--revision", type=int, required=True); reconcile_bindings.add_argument("--manifest", required=True)
    rehearse_recovery = sub.add_parser("rehearse-legacy-recovery", help="read-only in-memory rehearsal using only frozen fixture artifacts"); rehearse_recovery.add_argument("--file", required=True); rehearse_recovery.add_argument("--binding-manifest", required=True); rehearse_recovery.add_argument("--finding-manifest", required=True)
    brief = sub.add_parser("brief"); brief.add_argument("--control-root", required=True); brief.add_argument("--run-id", required=True); brief.set_defaults(brief=True)
    view = sub.add_parser("render-view"); view.add_argument("--control-root", required=True); view.add_argument("--run-id", required=True); view.add_argument("--kind", choices=["status", "final-report"], default="status")
    valid = sub.add_parser("validate"); valid.add_argument("--file", required=True); valid.add_argument("--kind", default="ledger")
    state_valid = sub.add_parser("validate-return"); state_valid.add_argument("--control-root", required=True); state_valid.add_argument("--run-id", required=True); state_valid.add_argument("--attempt-id", required=True); state_valid.add_argument("--return-file", required=True); state_valid.add_argument("--kind", choices=["worker", "review", "acceptance"], required=True)
    ingest = sub.add_parser("ingest-return"); ingest.add_argument("--control-root", required=True); ingest.add_argument("--run-id", required=True); ingest.add_argument("--owner-token", required=True); ingest.add_argument("--revision", type=int, required=True); ingest.add_argument("--attempt-id", required=True); ingest.add_argument("--return-file", required=True); ingest.add_argument("--kind", default="worker"); ingest.add_argument("--integrity-receipt")
    observe_runtime = sub.add_parser("observe-runtime", help="record an immutable, attempt-bound native runtime observation"); observe_runtime.add_argument("--control-root", required=True); observe_runtime.add_argument("--run-id", required=True); observe_runtime.add_argument("--owner-token", required=True); observe_runtime.add_argument("--revision", type=int, required=True); observe_runtime.add_argument("--attempt-id", required=True); observe_runtime.add_argument("--event", choices=["start", "heartbeat", "return_observed", "stop", "not_started"], required=True); observe_runtime.add_argument("--event-id", required=True); observe_runtime.add_argument("--event-file", required=True)
    dispatch = sub.add_parser("dispatch"); dispatch.add_argument("--control-root", required=True); dispatch.add_argument("--run-id", required=True); dispatch.add_argument("--owner-token", required=True); dispatch.add_argument("--revision", type=int, required=True); dispatch.add_argument("--ticket-id", required=True); dispatch.add_argument("--attempt-id", required=True); dispatch.add_argument("--lease-id", required=True); dispatch.add_argument("--route-id", required=True); dispatch.add_argument("--packet", required=True); dispatch.add_argument("--route")
    ready = sub.add_parser("ready-ticket"); ready.add_argument("--control-root", required=True); ready.add_argument("--run-id", required=True); ready.add_argument("--owner-token", required=True); ready.add_argument("--revision", type=int, required=True); ready.add_argument("--ticket-id", required=True)
    repair = sub.add_parser("authorize-repair"); repair.add_argument("--control-root", required=True); repair.add_argument("--run-id", required=True); repair.add_argument("--owner-token", required=True); repair.add_argument("--revision", type=int, required=True); repair.add_argument("--ticket-id", required=True); repair.add_argument("--finding-ref"); repair.add_argument("--authorization-id", required=True); repair.add_argument("--repair-contract", required=True); repair.add_argument("--packet"); repair.add_argument("--route-id"); repair.add_argument("--route")
    revoke_repair = sub.add_parser("revoke-repair"); revoke_repair.add_argument("--control-root", required=True); revoke_repair.add_argument("--run-id", required=True); revoke_repair.add_argument("--owner-token", required=True); revoke_repair.add_argument("--revision", type=int, required=True); revoke_repair.add_argument("--authorization-id", required=True); revoke_repair.add_argument("--revocation-id", required=True); revoke_repair.add_argument("--reason", required=True)
    close_blocked = sub.add_parser("close-blocked-attempt", aliases=["restore-last-validated-candidate"]); close_blocked.add_argument("--control-root", required=True); close_blocked.add_argument("--run-id", required=True); close_blocked.add_argument("--owner-token", required=True); close_blocked.add_argument("--revision", type=int, required=True); close_blocked.add_argument("--ticket-id", required=True); close_blocked.add_argument("--attempt-id", required=True)
    finalize_attempt = sub.add_parser("finalize-attempt"); finalize_attempt.add_argument("--control-root", required=True); finalize_attempt.add_argument("--run-id", required=True); finalize_attempt.add_argument("--owner-token", required=True); finalize_attempt.add_argument("--revision", type=int, required=True); finalize_attempt.add_argument("--ticket-id", required=True); finalize_attempt.add_argument("--attempt-id", required=True)
    reconcile_finalized = sub.add_parser("reconcile-finalized-attempt"); reconcile_finalized.add_argument("--control-root", required=True); reconcile_finalized.add_argument("--run-id", required=True); reconcile_finalized.add_argument("--owner-token", required=True); reconcile_finalized.add_argument("--revision", type=int, required=True); reconcile_finalized.add_argument("--ticket-id", required=True); reconcile_finalized.add_argument("--attempt-id", required=True); reconcile_finalized.add_argument("--evidence", required=True)
    reconcile_quarantine = sub.add_parser("reconcile-quarantined-attempt"); reconcile_quarantine.add_argument("--control-root", required=True); reconcile_quarantine.add_argument("--run-id", required=True); reconcile_quarantine.add_argument("--owner-token", required=True); reconcile_quarantine.add_argument("--revision", type=int, required=True); reconcile_quarantine.add_argument("--ticket-id", required=True); reconcile_quarantine.add_argument("--attempt-id", required=True); reconcile_quarantine.add_argument("--prior-attempt-id", required=True); reconcile_quarantine.add_argument("--finding-ref", required=True); reconcile_quarantine.add_argument("--candidate-sha", required=True); reconcile_quarantine.add_argument("--base-sha", required=True); reconcile_quarantine.add_argument("--baseline", help="optional pre-attempt manifest; omitted means derive the complete baseline from the exact Git base tree"); reconcile_quarantine.add_argument("--reconciliation-id", required=True); reconcile_quarantine.add_argument("--actor", required=True)
    terminate = sub.add_parser("terminate-attempt"); terminate.add_argument("--control-root", required=True); terminate.add_argument("--run-id", required=True); terminate.add_argument("--owner-token", required=True); terminate.add_argument("--revision", type=int, required=True); terminate.add_argument("--attempt-id", required=True); terminate.add_argument("--state", choices=["LOST", "INTERRUPTED"], required=True); terminate.add_argument("--lease-state", choices=["released", "quarantined"], required=True); terminate.add_argument("--evidence", required=True)
    candidate = sub.add_parser("candidate"); candidate.add_argument("--control-root", required=True); candidate.add_argument("--run-id", required=True); candidate.add_argument("--owner-token", required=True); candidate.add_argument("--revision", type=int, required=True); candidate.add_argument("--attempt-id", required=True); candidate.add_argument("--commit-receipt", required=False); candidate.add_argument("--operation-id", required=True)
    continuation_candidate = sub.add_parser("preserve-blocked-candidate"); continuation_candidate.add_argument("--control-root", required=True); continuation_candidate.add_argument("--run-id", required=True); continuation_candidate.add_argument("--owner-token", required=True); continuation_candidate.add_argument("--revision", type=int, required=True); continuation_candidate.add_argument("--ticket-id", required=True); continuation_candidate.add_argument("--attempt-id", required=True); continuation_candidate.add_argument("--authorization-file", required=True); continuation_candidate.add_argument("--commit-receipt", required=True); continuation_candidate.add_argument("--operation-id", required=True)
    effect = sub.add_parser("prepare-effect"); effect.add_argument("--control-root", required=True); effect.add_argument("--run-id", required=True); effect.add_argument("--owner-token", required=True); effect.add_argument("--revision", type=int, required=True); effect.add_argument("--operation-id", required=True); effect.add_argument("--kind", required=True); effect.add_argument("--target", required=True); effect.add_argument("--expected-before", default=None); effect.add_argument("--intended-after", default=None); effect.add_argument("--authority-ref", required=True)
    reconcile_effect = sub.add_parser("reconcile-effect"); reconcile_effect.add_argument("--control-root", required=True); reconcile_effect.add_argument("--run-id", required=True); reconcile_effect.add_argument("--owner-token", required=True); reconcile_effect.add_argument("--revision", type=int, required=True); reconcile_effect.add_argument("--operation-id", required=True); reconcile_effect.add_argument("--result", choices=["applied", "uncertain", "abandoned", "unchanged"], required=True); reconcile_effect.add_argument("--receipt")
    review = sub.add_parser("prepare-review"); review.add_argument("--control-root", required=True); review.add_argument("--run-id", required=True); review.add_argument("--owner-token", required=True); review.add_argument("--revision", type=int, required=True); review.add_argument("--ticket-id", required=True); review.add_argument("--review-attempt-id", required=True); review.add_argument("--lease-id", required=True); review.add_argument("--packet", required=True)
    design_review = sub.add_parser("prepare-design-review"); design_review.add_argument("--control-root", required=True); design_review.add_argument("--run-id", required=True); design_review.add_argument("--owner-token", required=True); design_review.add_argument("--revision", type=int, required=True); design_review.add_argument("--review-attempt-id", required=True); design_review.add_argument("--lease-id", required=True); design_review.add_argument("--packet", required=True); design_review.add_argument("--review-kind", choices=["coverage", "plan"], required=True); design_review.add_argument("--reviewer-identity", required=True); design_review.add_argument("--reviewer-role", required=True)
    adjudicate = sub.add_parser("adjudicate"); adjudicate.add_argument("--control-root", required=True); adjudicate.add_argument("--run-id", required=True); adjudicate.add_argument("--owner-token", required=True); adjudicate.add_argument("--revision", type=int, required=True); adjudicate.add_argument("--decision-file", required=True)
    integrate = sub.add_parser("integrate"); integrate.add_argument("--control-root", required=True); integrate.add_argument("--run-id", required=True); integrate.add_argument("--owner-token", required=True); integrate.add_argument("--revision", type=int, required=True); integrate.add_argument("--qualification-ref"); integrate.add_argument("--attempt-id"); integrate.add_argument("--review-file"); integrate.add_argument("--integrity-receipt"); integrate.add_argument("--review-id")
    handoff = sub.add_parser("prepare-handoff"); handoff.add_argument("--control-root", required=True); handoff.add_argument("--run-id", required=True); handoff.add_argument("--owner-token", required=True); handoff.add_argument("--revision", type=int, required=True); handoff.add_argument("--attempt-id", required=True); handoff.add_argument("--packet", required=True); handoff.add_argument("--projection", required=True); handoff.add_argument("--export-root", required=True); handoff.add_argument("--bundle-root", required=True); handoff.add_argument("--purpose", choices=["ticket_change", "ticket_review", "critical_axis", "final_g5"])
    manual = sub.add_parser("import-manual"); manual.add_argument("--control-root", required=True); manual.add_argument("--run-id", required=True); manual.add_argument("--owner-token", required=True); manual.add_argument("--revision", type=int, required=True); manual.add_argument("--attempt-id", required=True); manual.add_argument("--return-file", required=True); manual.add_argument("--environment-receipt", required=True); manual.add_argument("--context-receipt", required=True); manual.add_argument("--integrity-receipt", required=True); manual.add_argument("--intent-revision", required=True); manual.add_argument("--candidate-fingerprint", required=True); manual.add_argument("--required-criteria", required=True); manual.add_argument("--purpose", choices=["ticket_change", "ticket_review", "critical_axis", "final_g5"])
    audit = sub.add_parser("audit-write-set"); audit.add_argument("--root", required=True); audit.add_argument("--baseline", required=True); audit.add_argument("--declared", required=True); audit.add_argument("--zone", required=True)
    gate = sub.add_parser("gate"); gate.add_argument("--control-root", required=True); gate.add_argument("--run-id", required=True); gate.add_argument("--owner-token", required=True); gate.add_argument("--revision", type=int, required=True); gate.add_argument("--phase"); gate.add_argument("--control"); gate.add_argument("--gate-id", choices=[f"G{i}" for i in range(7)]); gate.add_argument("--reason", default=None); gate.add_argument("--next-action", default="inspect"); gate.add_argument("--subject-refs", default=""); gate.add_argument("--preconditions", default=""); gate.add_argument("--read-refs", default="")
    cancel = sub.add_parser("cancel"); cancel.add_argument("--control-root", required=True); cancel.add_argument("--run-id", required=True); cancel.add_argument("--owner-token", required=True); cancel.add_argument("--revision", type=int, required=True); cancel.add_argument("--reason", default="user_cancelled"); cancel.add_argument("--stop-target", default=None); cancel.add_argument("--finalize", action="store_true"); cancel.add_argument("--stop-evidence")
    recover = sub.add_parser("recover"); recover.add_argument("--control-root", required=True); recover.add_argument("--run-id", required=True); recover.add_argument("--owner-token", required=True); recover.add_argument("--revision", type=int, required=True); recover.add_argument("--reason", default="recovery"); recover.add_argument("--takeover", action="store_true"); recover.add_argument("--new-owner-token", default=None); recover.add_argument("--attestation-ref", default=None)
    initial_intent = sub.add_parser("publish-intent"); initial_intent.add_argument("--control-root", required=True); initial_intent.add_argument("--run-id", required=True); initial_intent.add_argument("--owner-token", required=True); initial_intent.add_argument("--revision", type=int, required=True); initial_intent.add_argument("--intent-file", required=True); initial_intent.add_argument("--doc-id", required=True); initial_intent.add_argument("--doc-version", required=True); initial_intent.add_argument("--intent-revision", required=True)
    requirements = sub.add_parser("adopt-requirements", aliases=["publish-requirements"]); requirements.add_argument("--control-root", required=True); requirements.add_argument("--run-id", required=True); requirements.add_argument("--owner-token", required=True); requirements.add_argument("--revision", type=int, required=True); requirements.add_argument("--manifest", required=True)
    currentness = sub.add_parser("migrate-review-currentness"); currentness.add_argument("--control-root", required=True); currentness.add_argument("--run-id", required=True); currentness.add_argument("--owner-token", required=True); currentness.add_argument("--revision", type=int, required=True)
    design = sub.add_parser("publish-design-bundle", aliases=["publish-design"]); design.add_argument("--control-root", required=True); design.add_argument("--run-id", required=True); design.add_argument("--owner-token", required=True); design.add_argument("--revision", type=int, required=True); design.add_argument("--bundle", required=True)
    amend = sub.add_parser("amend"); amend.add_argument("--control-root", required=True); amend.add_argument("--run-id", required=True); amend.add_argument("--owner-token", required=True); amend.add_argument("--revision", type=int, required=True); amend.add_argument("--intent-file", required=True); amend.add_argument("--doc-id", required=True); amend.add_argument("--doc-version", required=True); amend.add_argument("--intent-revision", required=True); amend.add_argument("--amendment-id", required=True); amend.add_argument("--authority-ref", required=True)
    usage = sub.add_parser("publish-usage"); usage.add_argument("--control-root", required=True); usage.add_argument("--run-id", required=True); usage.add_argument("--owner-token", required=True); usage.add_argument("--revision", type=int, required=True); usage.add_argument("--event-file", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init": result = cmd_init(args)
        elif args.command == "status": result = cmd_status(args)
        elif args.command == "diagnose": result = cmd_diagnose(args)
        elif args.command == "diagnose-legacy": result = cmd_diagnose_legacy(args)
        elif args.command == "assess-legacy-bindings": result = _cmd_assess_legacy_bindings(args)
        elif args.command == "migrate-legacy-bindings": result = _cmd_migrate_legacy_bindings(args)
        elif args.command == "reconcile-finding-bindings": result = _cmd_reconcile_finding_bindings(args)
        elif args.command == "rehearse-legacy-recovery": result = _cmd_rehearse_legacy_recovery(args)
        elif args.command == "brief": result = cmd_status(args)
        elif args.command == "render-view": result = cmd_render_view(args)
        elif args.command == "validate": result = cmd_validate(args)
        elif args.command == "validate-return": result = cmd_validate_return(args)
        elif args.command == "ingest-return": result = cmd_ingest(args)
        elif args.command == "observe-runtime": result = cmd_observe_runtime(args)
        elif args.command == "dispatch": result = cmd_dispatch(args)
        elif args.command == "ready-ticket": result = cmd_ready_ticket(args)
        elif args.command == "authorize-repair": result = cmd_authorize_repair(args)
        elif args.command == "revoke-repair": result = cmd_revoke_repair(args)
        elif args.command in ("close-blocked-attempt", "restore-last-validated-candidate"): result = cmd_close_blocked_attempt(args)
        elif args.command == "finalize-attempt": result = cmd_finalize_attempt(args)
        elif args.command == "reconcile-finalized-attempt": result = cmd_reconcile_finalized_attempt(args)
        elif args.command == "reconcile-quarantined-attempt": result = cmd_reconcile_quarantined_attempt(args)
        elif args.command == "terminate-attempt": result = cmd_terminate_attempt(args)
        elif args.command == "candidate": result = cmd_candidate(args)
        elif args.command == "preserve-blocked-candidate": result = cmd_preserve_blocked_candidate(args)
        elif args.command == "prepare-effect": result = cmd_prepare_effect(args)
        elif args.command == "reconcile-effect": result = cmd_reconcile_effect(args)
        elif args.command == "prepare-review": result = cmd_prepare_review(args)
        elif args.command == "prepare-design-review": result = cmd_prepare_design_review(args)
        elif args.command == "adjudicate": result = cmd_adjudicate(args)
        elif args.command == "integrate": result = cmd_integrate(args)
        elif args.command == "prepare-handoff": result = cmd_prepare_handoff(args)
        elif args.command == "import-manual": result = cmd_import_manual(args)
        elif args.command == "audit-write-set": result = cmd_audit(args)
        elif args.command == "gate": result = cmd_gate(args)
        elif args.command == "cancel": result = cmd_cancel(args)
        elif args.command == "recover": result = cmd_recover(args)
        elif args.command == "publish-intent": result = cmd_publish_intent(args)
        elif args.command in ("adopt-requirements", "publish-requirements"): result = cmd_adopt_requirements(args)
        elif args.command == "migrate-review-currentness": result = cmd_migrate_review_currentness(args)
        elif args.command in ("publish-design-bundle", "publish-design"): result = cmd_publish_design_bundle(args)
        elif args.command == "amend": result = cmd_amend(args)
        elif args.command == "publish-usage": result = cmd_publish_usage(args)
        else: fail(f"unsupported command: {args.command}")
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except LedgerError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": f"safe helper failure: {exc}"}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
