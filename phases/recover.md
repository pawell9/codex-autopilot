# Recovery, pause, and cancellation

Use this file for pause, quota, resume, lost handles, uncertain Git effects, owner transfer, state mismatch, or cancellation. Read `references/ledger.md` and `references/safety.md` before any effect. Recovery does not execute product tickets.

## Stop guard

On pause, quota, cancellation, unsafe activity, or material amendment, enter `QUIESCING`, stop new dispatch, interrupt active agents/commands, and record partial state. Do not assume a missing UI handle, quiet filesystem, process absence, or epoch change proves termination. Confirm all known writers and background tools stopped, or keep the checkout quarantined.

Pause preserves worktree and changes. Cancel records the goal termination, preserves owned partial state, and does not reset, stash, clean, delete foreign files, or silently clean a worktree. Cleanup is optional and later requires exact ownership, stopped processes, and a retained checkpoint.

## Reconciliation

1. Under the fixed owner lock, validate current and `ledger.prev.json`, owner token/epoch, run identity, revisions, canonical document hashes, attempts, leases, inboxes, and prepared operations.
2. Reconcile actual checkout HEAD/ref/index/worktree and operation targets against prepared evidence. A commit with missing receipt is accepted only when old HEAD, intended tree, operation trailer, and resulting SHA match; otherwise the operation is uncertain and is not repeated.
3. For spawn loss, inspect registered handles/processes, attempt inbox, partial files, and writing activity. Stop confirmed writers. A user attestation may cover closure of the old session and its background writers only when corroborating observations do not conflict; it is recorded as evidence, not as runtime proof.
4. Apply the reuse guard: runtime-confirmed stop of all writing activity, or the explicit attestation plus bounded process/checkout observations. `ps`, `lsof`, and file quiet are corroboration only. If the guard is unmet, keep the lease quarantined and set `agent_liveness_unknown` with the exact action to stop/confirm writers.
5. Audit foreign tracked/untracked/ignored changes, symlink targets, protected paths, and Git common-dir state. Preserve foreign fingerprints. Old-epoch returns are historical evidence until the current owner re-audits and accepts them by version/subject checks.
6. Invalidate facts affected by build, permission, surface, repo, HEAD, instruction, toolchain, configuration, or contradictory observations. Set the earliest invalid gate and a precise `next_action`.

Use `tools/ledger.py recover` for deterministic publication. If current JSON is corrupt, validate verified previous snapshots newest-first; do not overwrite the namespace with a guessed reconstruction. An unknown schema is a read-only migration diagnostic. If no safe recovery exists, remain `BLOCKED` or `FAILED` after all in-flight activity is stopped; a successor run needs an explicit new scope decision.

## Handoff and resume

Before human or context handoff, persist phase/control, candidate/base, pending operations, leases, packet/export/return refs, completed/remaining criteria, unresolved decisions, receipt requirements, and exact next action. On resume, reread `SKILL.md`, the current phase, and relevant safety/routing rules, then obtain a fresh brief and reconcile actual state. A valid nonterminal ledger with no `intent` is an incomplete bootstrap: keep the same run and use `publish-intent` with the current owner/revision and existing authorized Markdown; do not create a successor or hand-edit state. Do not resend a bundle or rerun a reviewer merely because the old chat/handle is gone. A lost output may be re-requested for the same unchanged subject; a changed candidate or intent requires a new packet/round.

**Done when:** every incomplete operation/attempt has a reconciled outcome or quarantine, foreign state is preserved, owner reuse is justified, and the next valid phase/action is durable.
