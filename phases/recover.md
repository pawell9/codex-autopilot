# Recovery, pause, and cancellation

Use this file for pause, quota, resume, lost handles, uncertain Git effects, owner transfer, state mismatch, or cancellation. Read `references/ledger.md` and `references/safety.md` before any effect. Recovery does not execute product tickets.

## Stop guard

On pause, quota, cancellation, unsafe activity, or material amendment, enter `QUIESCING`, stop new dispatch, interrupt active agents/commands, and record partial state. Do not assume a missing UI handle, quiet filesystem, process absence, timeout, absent heartbeat, user attestation, or epoch change proves producer termination. Publish exact attempt-bound `observe-runtime` receipts from the external runtime, or keep the checkout reservation quarantined.

Pause preserves worktree and changes. Cancel records the goal termination, preserves owned partial state, and does not reset, stash, clean, delete foreign files, or silently clean a worktree. Cleanup is optional and later requires exact ownership, stopped processes, and a retained checkpoint.

## Reconciliation

1. Under the fixed owner lock, validate current and `ledger.prev.json`, owner token/epoch, run identity, revisions, canonical document hashes, attempts, leases, inboxes, and prepared operations.
2. Reconcile actual checkout HEAD/ref/index/worktree and operation targets against prepared evidence. A candidate commit is recorded `applied` only from a fresh immutable receipt bound to the exact operation, run/ticket/attempt, checkout target, base, authority, resulting commit/tree, and actual clean Git state. `applied` is not repeated: use the derived `adopt_applied_effect` action to run the shared candidate proof and atomically finalize its linkage. Missing or conflicting proof remains `uncertain` and is not repeated.
3. For spawn loss, inspect registered handles/processes, attempt inbox, partial files, and writing activity. The external runtime adapter records `start`, optional `heartbeat`/`return_observed`, then exact `stop` with `coverage.descendant_writers=included`; a `return_observed` event only binds the return hash and never proves stop. Record `not_started` only when no process was started and no return was produced. User attestation may support takeover of the orchestration owner, but it is not a producer-stop receipt.
4. Apply the mutation/reuse guard: require the exact typed stop receipt for the attempt and runtime instance, including descendant writers, or valid `not_started` receipt when no instance/return exists. `ps`, `lsof`, file quiet, timeout, and absent heartbeat may corroborate but cannot replace that receipt. Missing runtime records on historical attempts remain explicitly `unknown`; candidate/review qualification, lease release, and reuse fail closed. Keep the lease quarantined and record the precise missing external observation when the guard is unmet.
   Record worker/reviewer outcome with `terminate-attempt` as appropriate; the
   workflow state and lease disposition publish atomically, but liveness is
   proven only by the referenced immutable runtime observation.
5. Audit foreign tracked/untracked/ignored changes, symlink targets, protected paths, and Git common-dir state. Preserve foreign fingerprints. Old-epoch returns are historical evidence until the current owner re-audits and accepts them by version/subject checks.
6. Invalidate facts affected by build, permission, surface, repo, HEAD, instruction, toolchain, configuration, or contradictory observations. Set the earliest invalid gate and a precise `next_action`.

Do not hand-edit a quarantined lease. A returned legacy repair attempt may be
restored to candidate authority only through `reconcile-quarantined-attempt`
and only for the provenance-bound same-ticket create-to-modify case documented
in `phases/execute.md`. A general quarantine already recorded by
`finalize-attempt` may use `reconcile-finalized-attempt` only after an exact
typed stop/not-started receipt with descendant-writer coverage and a fresh
checkout audit prove the checkout is exactly the verified base or retained
candidate. The helper validates the external claim; it does not stop/kill
native workers or independently enumerate their descendants. This path discards partial work; it never
turns unknown or foreign writes into a candidate. Failed proof, stale base,
pending effects, or incomplete cleanup remains explicitly quarantined.

Use `tools/ledger.py recover` for deterministic publication. If current JSON is corrupt, validate verified previous snapshots newest-first; do not overwrite the namespace with a guessed reconstruction. Use `diagnose` for an unknown schema; it is strictly read-only. If no safe recovery exists, remain `BLOCKED` or `FAILED` after all in-flight activity is stopped; a successor run needs an explicit new scope decision and a fresh namespace initialized with `init-successor` from a typed successor manifest binding exact predecessor evidence.

## Handoff and resume

Before human or context handoff, persist phase/control, candidate/base, pending operations, leases, packet/export/return refs, completed/remaining criteria, unresolved decisions, receipt requirements, and exact next action. On resume, reread `SKILL.md`, the current phase, and relevant safety/routing rules, then obtain a fresh brief and reconcile actual state. A valid nonterminal ledger with no `intent` is an incomplete bootstrap: keep the same run and use `publish-intent` with the current owner/revision and existing authorized Markdown; do not create a successor or hand-edit state. Do not resend a bundle or rerun a reviewer merely because the old chat/handle is gone. A lost output may be re-requested for the same unchanged subject; a changed candidate or intent requires a new packet/round.

**Done when:** every incomplete operation/attempt has a reconciled outcome or quarantine, foreign state is preserved, owner reuse is justified, and the next valid phase/action is durable.
