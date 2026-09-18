# Start and preflight

Use this file for a new invocation, resume precheck, or environment recheck. Read `references/ledger.md` for transactions and `references/safety.md` for Git/path effects.

## G0 sequence

1. Classify the explicit request as `start`, `resume`, `status`, `pause`, or `cancel`. Preserve the user's exact target, requested authority, expected observable outcome, exclusions, and any requirement for human acceptance. An ordinary edit is not an Autopilot run.
   For `start`, resolve `run_settings.interaction_mode` (`semi` or `full`) and `run_settings.depth` (`normal` or `deep`) from obvious Russian/English wording. Use `semi + normal` when omitted or ambiguous, persist the result before dispatch, and briefly show the resolved labels. Do not implement native argument autocomplete or change presets mid-run.
2. Resolve the exact requested repository root. Inspect Git identity, common directory, branch/HEAD, staged/unstaged/untracked/ignored inventory, symlink roots, and applicable instruction files. A nested, bare, submodule-mutating, remote, or unsupported OS target is diagnostic/blocking; do not substitute a nearby repository.
3. Resolve the repository-wide owner registry/lock and the run path `<control-root>/.autopilot/runs/<run-id>`. Only one nonterminal run may own a repository identity. Existing nonterminal state is recovered, never overwritten. A terminal run is read-only; a changed scope uses a fresh namespace and `init-successor` with a schema-validated manifest binding the exact terminal predecessor, accepted evidence, candidate/resources, scope decision, exclusions, and unknowns. Do not copy live attempts or reservations into a successor.
4. Validate schema, current ledger revision, owner token/epoch, referenced document hashes, pending operations, leases, and `next_action`. Use `tools/ledger.py status` or `brief`; do not hand-edit JSON. After a new `init`, write the authorized canonical intent input outside the ledger and call `tools/ledger.py publish-intent` with the current revision, document ID/version, and intent revision. The command is the only initial binding path and rejects a second initial intent; later changes use `amend`.
5. For a new or greenfield target, record the pre-bootstrap inventory, then perform only the scoped Git init/initial commit allowed by `references/safety.md`. Never stage with `git add -A`, copy secrets, reset user work, or edit global config. No-commit policy blocks execution.
6. Run cheap capability checks. Record confirmed, rejected, or unknown facts with evidence, observed time, scope, and fingerprint. Check the native spawn/control surface, Python 3 stdlib, Git, writable canonical namespace, effective approval boundary, and the selected surface/build. `codex --version` is not active-session identity.
7. Run a conditional probe only for the next real need: worker dispatch, routine review, Git action/worktree, oracle, network/install, or manual critical/G5 handoff. Reuse a fact only when its fingerprint still matches. Unknown safety or required authority blocks the dependent transition.

## Supported boundary

The supported target is a local macOS CLI/app/IDE session with a permanent Git checkout, native bounded workers, routine review on a frozen export, and a user-assisted isolated clean session for critical axes/G5. Linux/Windows/WSL, cloud/web/remote control stores, managed ephemeral authority checkouts, and `codex exec` as an unqualified worker/reviewer transport receive a precise diagnostic rather than an execution promise.

At G0 disclose that routine bookkeeping and bundle preparation are automatic, while the user must set up/transfer the critical/G5 bundle and return the exact reviewer result with setup/context receipts. Do not call that capability qualified merely because a session can be opened. Fully automatic strict G5 is not a V1 route.

## Resume branch

On resume, enter `RECOVERING` before product dispatch. Reconcile current and previous ledger publications, actual Git state, operations, inboxes, handles/process observations, instructions, capability invalidation, and owner epoch. A missing UI handle is not proof of stop. Use `phases/recover.md` for uncertain liveness. If a valid nonterminal run has no initial intent, preserve the run and publish the existing authorized canonical intent with `publish-intent`; a matching same-byte document left by an interrupted publication is reusable. Then set the earliest invalid phase and an exact durable `next_action`; only after reconciliation return to `ACTIVE`.

**Done when:** the exact repository, namespace, owner, phase/control, capabilities, authority, baseline, and next safe action are durable, or the run has a precise `BLOCKED_PREFLIGHT`/`BLOCKED` diagnostic with no product dispatch. Repository ownership prevents competing ledger owners; it does not establish producer liveness or stop processes.
