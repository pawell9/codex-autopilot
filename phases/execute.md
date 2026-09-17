# Execute, review, and G4

Read `contracts/worker.md`, `contracts/reviewer.md`, `references/ledger.md`, `references/routing.md`, and `references/safety.md` for the branch you are about to run. The normal loop is one bounded worker attempt at a time.

## Ticket loop

1. Materialize a READY ticket with `ready-ticket` only when dependencies are reviewed/current `INTEGRATED`, packet/contract/criterion refs belong to the current publication, the literal zone is non-overlapping, the lease is free, the oracle is available, and the route is resolved.
2. Generate the minimal immutable packet and hash. It must include identity, one observable goal, inline criteria, exact workspace/base, lease allow/deny, verification scenarios, risk, relevant pointers, and exact return target. Persist `PREPARED` before native spawn.
3. Spawn one new bounded native worker for a new ticket. A repair attempt uses `mode=repair` and accepted findings. The worker may be `DEGRADED_CONTEXT` only under the worker eligibility rules; the orchestrator never edits product as fallback. Missing worker capability blocks execution.
4. Worker verifies root, base, instructions, criteria, and zone before the first write. It returns `DONE`, `BLOCKED`, `FAILED`, or `HANDOFF` through the exact file inbox or message contract. `await_worker_return` is an internal action: remain in the current orchestration turn and wait for this exact registered attempt in intervals of at most 60 seconds. After three consecutive no-progress intervals, inspect the handle and exact inbox, interrupt/stop if possible, and route through LOST/INTERRUPTED recovery; do not ask the user to continue routine execution and never invent DONE. A timeout is not proof that the writer stopped, so release the lease only with stop evidence and otherwise quarantine it.
5. Run read-only `validate-return` and ingest only a matching attempt/packet/contract/epoch/registration/subject return. Independently audit actual tracked, untracked, relevant ignored, type, rename, symlink, protected, and foreign changes. An undeclared effect quarantines the checkout and creates an ownership issue. Exact duplicate bytes are zero-effect; conflicting duplicates are rejected.
6. Prepare the exact Git candidate effect. The orchestrator uses the normal approved Git boundary, never raw `.git` edits or a helper bypass. Verify base, intended tree, audited paths, hook effects, candidate SHA, clean index/worktree, and operation receipt. A nonempty candidate commit precedes review; a no-op keeps the existing SHA and requires evidence.
7. Freeze the candidate and prepare a fresh `change` reviewer packet on the immutable SHA. Routine review uses the qualified export/barrier path. Elevated work adds the risk mandate; critical work adds a separate independent security/data/trust axis. Reviewers never receive worker self-rating or repair authority.
8. Stop the reviewer, run the independent integrity barrier, and ingest its exact structured return. A subject/state/docs/evidence mismatch invalidates the verdict and quarantines the target. PASS on an altered or unverified subject is not PASS.
9. On required PASS, mechanically verify integration and release the reservation; mark the ticket `INTEGRATED`. On a finding, preserve the immutable verdict, triage cause first, and use `authorize-repair` before repair dispatch. Semantic integration conflicts become worker integration-repair tickets. Do not batch away a blocking issue.

If a repair returns `BLOCKED` before any write, do not feed that candidate-less
attempt into a new authorization and do not hand-release its lease. Run
`close-blocked-attempt` only when the stored return is exact and declares
`files=[]`; the command independently proves a clean checkout at the attempt
base, derives the immediate previous validated candidate, preserves the full
attempt history, releases the lease, and restores `ticket.current_attempt`.
Afterward create a changed repair contract and use normal `authorize-repair`.

## Cause-first repair

`implementation` routes to a minimal worker repair with changed hypothesis and regression proof. `contract` or `user_intent` returns through versioned INTENT/DESIGN/PLAN. `oracle` reconstructs expected behavior independently. `environment`/`permission` performs a conditional preflight or records a user action. `ownership` quarantines and resolves the exact zone/base. `orchestration` reconciles ledger/attempt/effect state. `unknown` gets a fresh read-only diagnosis.

A repair lease is still packet-scoped. The sole cumulative exception is an
exact same-ticket chain `create → candidate → repair modify → candidate →
repair modify ...`. The repair packet must use the current worker candidate
SHA as its base and name either that worker or the exact finding review. Every
candidate/base edge must be continuous; every modify hop must carry its own
accepted blocking finding and consumed authorization; and the chain must end
at a validated DONE create return inside the original ticket create zone. The
current packet must independently allow the exact modify path. The attempt
stores the complete path-specific lineage, including every worker candidate,
return, finding, and authorization. `authorize-repair` stores the exact
repair-contract object, and one authorization is consumed by one repair
attempt. A stale or forked base, other ticket, foreign path, broken provenance,
packet-denied path, missing original create, or any other operation is
rejected; quarantined provenance is never reused or auto-released. An already
quarantined legacy repair return may use `reconcile-quarantined-attempt` only
when the exact current attempt, prior DONE create attempt, accepted blocking
finding, authorization, candidate/base SHA, packet allow/deny scope, and a
fresh actual write-set audit all agree. The command records actor, inputs,
fingerprints, issue refs, and the derived lease in an immutable receipt, is
idempotent for the same evidence, and leaves every failed proof quarantined.

Retry only after a confirmed transient cause and effect reconciliation. A repeat requires a changed causal input, approach, capability, or evidence and an expected distinguishing result. Repeated same-class failure first gets a diagnostic checkpoint; no arbitrary repair counter or automatic success exists. Fresh context is required after amendment, lost/context-saturated worker, or repeated causal defect after substantive repair.

## G4

When required tickets are current `INTEGRATED`, all leases are closed/reserved correctly, the changeset is frozen, and integration checks pass, publish G4. Any unresolved blocking issue, stale criterion, unexpected write, missing oracle, or pending effect keeps the run in `VERIFY`/`BLOCKED` as appropriate. Then route to `phases/accept.md` for G5; G4 is not final acceptance.

**Done when:** every required ticket has independently reviewed evidence and an audited candidate/integration record, or the run has a durable cause-specific blocker and safe next action.
