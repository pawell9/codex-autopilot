# Execute, review, and G4

Read `contracts/worker.md`, `contracts/reviewer.md`, `references/ledger.md`, `references/routing.md`, and `references/safety.md` for the branch you are about to run. The normal loop is one bounded worker attempt at a time.

## Ticket loop

1. Materialize a READY ticket with `ready-ticket` only when dependencies are reviewed/current `INTEGRATED`, packet/contract/criterion refs belong to the current publication, the literal zone is non-overlapping, the lease is free, the oracle is available, and the route is resolved.
2. Generate the minimal immutable packet and hash. It must include identity, one observable goal, inline criteria, exact workspace/base, lease allow/deny, verification scenarios, risk, relevant pointers, and exact return target. The registration binds an immutable execution snapshot (checkout/base, intent and design publication, criteria/contracts, route, and packet); persist `PREPARED` before any external spawn.
3. Dispatch/review preparation is registration only: it increments `attempt_registrations`, returns a stable `spawn_request_id` and a `register_only_use_spawn_request_id_once` disposition, and does not spawn or increment `spawn_calls`. The external runtime adapter must consume that ID once and publish a typed `start` receipt with `observe-runtime`. Only the first valid start increments `spawn_calls`. An exact registration replay reports `existing_request_do_not_spawn_again`; it is not spawn authorization. A repair attempt uses `mode=repair` and accepted findings. Missing worker/runtime capability blocks execution.
4. The adapter may publish exact-attempt `heartbeat`, `return_observed`, and `stop` events. A normal worker return is not a stop receipt: `return_observed` binds the return hash but does not prove liveness ended. A typed `not_started` receipt is valid only when the registered attempt truly never started and has no runtime return. `await_worker_return` is an internal action: remain in the current orchestration turn and wait for this exact registered attempt in intervals of at most 60 seconds. After three consecutive no-progress intervals, inspect the handle and exact inbox, request/perform external stop if possible, and route through LOST/INTERRUPTED recovery; do not ask the user to continue routine execution. A timeout or missing heartbeat remains `unknown`, never proof of stop.
5. Worker verifies root, base, instructions, criteria, and zone before the first write. It returns `DONE`, `BLOCKED`, `FAILED`, or `HANDOFF` through the exact file inbox or message contract. Run read-only `validate-return` and ingest only a matching attempt/packet/contract/epoch/registration/subject return. Independently audit actual tracked, untracked, relevant ignored, type, rename, symlink, protected, and foreign changes. An undeclared effect quarantines the checkout and creates an ownership issue. Exact duplicate bytes are zero-effect; conflicting duplicates are rejected. A checkout lease is only a reservation, not liveness; candidate/review qualification and release/reuse require an exact stop receipt whose descendant-writer coverage is `included`, or a valid `not_started` receipt. Otherwise retain/quarantine the reservation, including for legacy attempts without a runtime record.
6. Prepare the exact Git candidate effect. The orchestrator uses the normal approved Git boundary, never raw `.git` edits or a helper bypass. Verify the receipt's run/ticket/attempt/operation/target/base/authority bindings, direct parent, resulting commit/tree, audited tracked/untracked/ignored/rename/type/mode/symlink paths, hook effects, and clean index/worktree. Publish the ordinary or continuation candidate only through the shared `VerifiedCandidateProof` finalizer. If recovery already proved the operation `applied`, adopt its immutable receipt and finalize the candidate without repeating Git. A nonempty candidate commit precedes review; a no-op keeps the existing SHA and requires evidence.
7. Freeze the candidate and prepare a fresh `change` reviewer packet on the immutable SHA. Preparation only registers a reviewer request; the external adapter starts it once with the returned stable spawn ID and observes its lifecycle as above. Routine review uses the qualified export/barrier path. Elevated work adds the risk mandate; critical work adds a separate independent security/data/trust axis. Reviewers never receive worker self-rating or repair authority.
8. Observe exact reviewer stop (including descendant-writer coverage), run the independent integrity barrier, and ingest its exact structured return. A subject/state/docs/evidence mismatch invalidates the verdict and quarantines the target. PASS on an altered or unverified subject is not PASS. A reviewer return by itself does not prove stop.
9. On required PASS, mechanically verify integration and release the reservation only under the exact runtime-stop/not-started guard; mark the ticket `INTEGRATED`. On a finding, preserve the immutable verdict, triage cause first, and use `authorize-repair` before repair dispatch. Semantic integration conflicts become worker integration-repair tickets. Do not batch away a blocking issue.

If a repair returns `BLOCKED` before any write, do not feed that candidate-less
attempt into a new authorization and do not hand-release its lease. Run
`close-blocked-attempt` only when the stored return is exact and declares
`files=[]`; the command independently proves a clean checkout at the attempt
base, derives the immediate previous validated candidate, preserves the full
attempt history, and restores `ticket.current_attempt`. It also requires an
exact typed stop/not-started receipt before releasing the reservation.
Afterward create a changed repair contract and use normal `authorize-repair`.

For a non-empty `BLOCKED`/`HANDOFF` return, use
`preserve-blocked-candidate` only when the focused ticket checks pass, all
remaining failed checks and unsatisfied BLOCKED criteria are explicitly bound to
a typed external/out-of-scope blocker, the exact worker lease and any repair
lineage still validate, an exact stop receipt covers the returned producer and
descendant writers, and the complete write-set audit passes. The owner
authorization file must cite the current blocker and exact return. Prepare a
`candidate_commit` operation using that authorization as `authority_ref`, make
one direct candidate commit on the attempt base through the approved Git
boundary, then pass its exact receipt to the helper. The helper rechecks HEAD,
tree, parent, clean checkout, packet return, lease, provenance, and actual
base-to-candidate paths before publishing the hash-addressed audit receipt.
It leaves the ticket and lifecycle `BLOCKED`, preserves the worker's original
verdict and blocker, and makes the candidate available for review or a later
authorized repair. A continuation-only candidate cannot be integrated. Any
in-scope failed check, failed/empty audit, unauthorized path, stale provenance,
or quarantined lease rejects the transition without a ledger publication.

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
repair-contract object and, when the current candidate crosses a create-only
path into repair modification, requires a current same-ticket
`source_attempt_ref` before publishing READY. One authorization is consumed by
one repair attempt. An unused older READY authorization that omitted this now
required source may be superseded by a fresh exact contract; the prior decision
remains historical and is invalidated by the replacement. A stale or forked
base, other ticket, foreign path, broken provenance,
packet-denied path, missing original create, or any other operation is
rejected; quarantined provenance is never reused or auto-released. An already
quarantined legacy repair return may use `reconcile-quarantined-attempt` only
when the exact current attempt, prior DONE create attempt, accepted blocking
finding, authorization, candidate/base SHA, packet allow/deny scope, and a
fresh actual write-set audit all agree. The command records actor, inputs,
fingerprints, issue refs, and the derived lease in an immutable receipt, is
idempotent for the same evidence, and leaves every failed proof quarantined.

Retry only after a confirmed transient cause and effect reconciliation. A repeat requires a changed causal input, approach, capability, or evidence and an expected distinguishing result. Repeated same-class failure first gets a diagnostic checkpoint; no arbitrary repair counter or automatic success exists. Fresh context is required after amendment, lost/context-saturated worker, or repeated causal defect after substantive repair.

For every returned `BLOCKED`/`HANDOFF`/`FAILED` or terminated
`LOST`/`INTERRUPTED` worker, use `finalize-attempt`. A clean no-change result
retains the explicit current `DONE`/`CONTINUATION` candidate, or returns an
initial no-candidate ticket to dispatchable `READY` at the verified base.
Owned non-empty work still needs the continuation/candidate path; unknown stop,
foreign writes, pending effects, or a broken base binding quarantine instead
of fabricating success. A later clean-disposal proof uses
`reconcile-finalized-attempt`, never a lease edit.

## G4

When required tickets are current `INTEGRATED`, all leases are closed/reserved correctly, the changeset is frozen, and integration checks pass, publish G4. Any unresolved blocking issue, stale criterion, unexpected write, missing oracle, or pending effect keeps the run in `VERIFY`/`BLOCKED` as appropriate. Then route to `phases/accept.md` for G5; G4 is not final acceptance.

**Done when:** every required ticket has independently reviewed evidence and an audited candidate/integration record, or the run has a durable cause-specific blocker and safe next action.
