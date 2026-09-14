# Ledger and artifact protocol

This is the state authority. JSON stores structured orchestration state; canonical prose/spec/interfaces remain immutable Markdown revisions referenced by path, version, and SHA-256. Generated views are projections. One orchestrator owner writes state through `tools/ledger.py`; workers receive only an exact scratch return grant.

## Namespace and envelope

```text
<control-root>/.autopilot/
├── owner.lock
├── runs/<run-id>/{ledger.json,ledger.prev.json,docs/,snapshots/,objects/,packets/,views/}
└── scratch/<run-id>/<attempt-id>/
```

The control root is the permanent primary checkout recorded by Git inventory. A run ID is path-safe and exclusive. Existing nonterminal state is recovered, never overwritten; terminal runs are read-only. `.autopilot/` is excluded only by its exact owned `.git/info/exclude` line when authorized; it is not a backup and may be removed by broad clean/stash/delete operations.

The ledger envelope includes `schema_version`, `run_id`, monotonic `revision`, `previous_publication_hash`, UTC timestamps, `skill_version`, `policy_version`, `repository`, `owner`, optional durable `run_settings`, `lifecycle`, and only the collections needed by the run. `run_settings` contains `interaction_mode` (`semi`/`full`) and `depth` (`normal`/`deep`); missing fields in legacy ledgers resolve to `semi + normal` without an in-place migration. `null` plus a reason means unknown; `[]` means verified absence; missing optional collections mean not applicable. IDs are immutable and references use IDs, never positions. SHA-256 proves stored-byte identity, not claim truth.

Required records are `repository/owner`, `lifecycle.next_action`, `documents/intent`, `requirements/criteria/contracts`, `decisions`, `tickets`, `attempts`, `issues`, `reviews/acceptance`, `operations`, `capabilities/routes`, `evidence`, and `usage` as applicable. Repairs and handoffs are attempt modes/payloads; blockers and concerns are typed issues; waves, ready queues, progress, and transition lists are derived. `INTEGRATED` is a workflow fact, not fulfillment without current evidence.

## Atomic publication

For every mutation, the helper acquires the fixed advisory owner lock, rereads the current ledger, checks owner token/epoch and expected revision, validates the entire proposed snapshot and semantic invariants, and writes the prior valid bytes to `ledger.prev.json`. It then writes a same-directory temporary file, flushes/fsyncs, atomically replaces `ledger.json`, and syncs the directory. If the previous backup fails, no new publication is accepted. Orphan temporary files/objects are harmless and never authority. Generated view failure does not roll back state.

`dispatch` publishes a valid READY check, route, lease, packet ref/hash, and `PREPARED` attempt before spawn. `candidate` ingests a matching worker return, records handle/stop/write audit, and accepts an orchestrator-supplied Git receipt before freezing a candidate and preparing review. `integrate` ingests exact review evidence, verifies integrity and PASS, then publishes current integration and next action. `gate`, `amend`, and `recover` are compound intent commands. `brief` and `status` are bounded reads.

The helper does not call models, spawn agents, hold a daemon loop, parse prose, or make substantive review decisions. It may validate a receipt from an approved native Git operation; it must not bypass approval by becoming an opaque shell wrapper.

## Semantic guards

- Legal run phases are `PREFLIGHT, INTENT, DESIGN, PLAN, EXECUTE, VERIFY, ACCEPT`; controls are `ACTIVE, QUIESCING, PAUSED, BLOCKED, RECOVERING, ACCEPTED, FAILED, CANCELLED`.
- Tickets move `PLANNED → READY → RUNNING → CANDIDATE → REVIEW → INTEGRATED`, with `BLOCKED, REPAIR, STALE, CANCELLED` as local branches. Attempts are `PREPARED, DISPATCHED, RETURNED, LOST, INTERRUPTED`.
- Only legal phase/control transitions are accepted. `ACCEPTED` requires a G5 PASS and G6 record. An amendment stales affected evidence; it does not reuse old acceptance.
- Ticket dependencies must be current reviewed `INTEGRATED` outcomes. DAG validation rejects cycles. Active/quarantined leases and stale epochs cannot be reused.
- A return is accepted only when attempt, packet hash, contract versions, owner epoch, subject fingerprint, and lease match. Late/stale payloads remain evidence without authority.
- A prepared effect with unknown result is reconciled by identity/base/tree/receipt evidence before any repeat. No exactly-once promise exists.

## Objects, docs, views, and inboxes

Copy validated returns, manifests, receipts, and review evidence into immutable `objects/<sha256>` before referencing them. Keep exact source bytes. Canonical Markdown amendments are written as new versions first; a user-edited referenced file causes hash mismatch and dependent gates stop until authority is adjudicated. Views carry run ID/source revision/hash/generated marker and can be regenerated.

An attempt inbox is exact, regular, non-symlink, bounded, and registered before dispatch. The producer writes a sibling temp file, flushes/closes it, and atomically renames to `return.json`; the producer then stops writing. Ingest rejects traversal, escape, symlink, size overflow, inconsistent bytes, conflicting duplicate hashes, and malformed/stale subjects. Same-hash duplicate ingestion is idempotent. Crash after rename may be imported after stop, integrity, and version checks without rerunning the agent.

## Recovery and retention

`ledger.prev.json` is the last valid publication. Recovery snapshots are selected copies at gates and before dangerous effects; retain the last eight unpinned snapshots plus pinned unresolved-operation/recovery/terminal-acceptance snapshots. Never prune referenced evidence/docs/packets or unresolved receipts, and never prune during corrupt-state diagnosis.

Owner takeover and checkout reuse are separate. Increment epoch only after planned handoff or explicit user attestation of old session and background-writer closure, plus available corroborating observations. Quarantine leases until all known writing activity is stopped and bounded process/checkout observations agree. Epoch does not stop processes. Then audit actual state, invalidate affected facts/gates, and publish the earliest safe next action. An unknown schema is read-only migration diagnosis.

**Completion:** each publication is lock-protected, revision/epoch-checked, schema/semantic-valid, atomically durable, and reconstructible from files plus Git; every uncertain effect has a quarantine/next action rather than a duplicate execution.
