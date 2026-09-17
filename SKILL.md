---
name: codex-autopilot
description: Run a scoped software change from current intent to an independently verified local Git result with durable gates and independent review.
---

# Codex Autopilot

Run one scoped software change from the user's current intent to an independently verified local Git result. Invoke this skill explicitly for `start`, `resume`, `status`, `pause`, or `cancel`; an ordinary edit remains an ordinary edit.

## Run presets

At start, resolve two independent durable settings: interaction mode (`semi` / `full`) and depth (`normal` / `deep`). Defaults are `semi + normal`; obvious Russian or English phrases such as `полный автомат, глубокая` are accepted, while ambiguous wording falls back to defaults. The resolved values are stored in the authoritative run ledger as `run_settings`, survive pause/resume and recovery, and are projected by status/dashboard. Existing ledgers without this optional field resolve to the defaults without migration.

`semi` is the baseline autonomous behavior: routine decisions proceed without per-ticket confirmation, while authority-sensitive, irreversible, credential, oracle, and existing safety gates remain. `full` removes only routine interaction friction and never weakens those gates. `deep` requests more thorough analysis, alternatives, acceptance wording, edge-case and failure-mode coverage; it is an orchestration hint only and does not select a model, add a reviewer, change a safety category, or create a lifecycle phase. Presets cannot be changed mid-run.

## Entry contract

The orchestrator owns the run ledger, canonical Markdown revisions, routing, packets, evidence, Git integration, and the final report. A bounded native worker owns product edits in one lease zone. An independent reviewer returns evidence and a verdict; it never repairs its own finding. The Python helper at `tools/ledger.py` is deterministic bookkeeping only: it does not call models, spawn agents, or decide substantive review outcomes.

For a new run, `init` creates revision 0 and `publish-intent` atomically binds the first canonical intent as revision 1 before G1 work continues. `publish-intent` is valid exactly once; use `amend` only after that binding exists. On resume, a nonterminal legacy or blocked run without `intent` publishes its existing authorized intent through this command instead of editing the ledger or starting a successor run.

After G1, publish a complete `design_bundle` containing the versioned design,
interfaces/contracts, manifest, implementation plan, tickets, routes, and
dependency bindings with `tools/ledger.py publish-design-bundle`. The
owner/epoch/revision-fenced transaction validates every source and the complete
proposed ledger before making any canonical binding visible. Same-byte retries
are idempotent; conflicting bundles or canonical documents are rejected.
`ticket.contract_refs` are executable inputs only; outputs remain expressed by
`contract.producer_refs`. A ticket may not require a contract it produces, and
an older mixed bundle is rejected rather than silently reinterpreted or having
its proposed contract activated. Then
register each independent G2 coverage or G3 plan review with
`prepare-design-review`, including reviewer identity and role. The attempt
binds the bundle fingerprint, artifact versions, intent revision, and
publication revision before dispatch. A current publication with a
BLOCK/UNVERIFIABLE coverage or plan review may be revised only in the
nonterminal DESIGN repair cycle. The new immutable publication is appended to
`design_publication_history`, the old publication and its review evidence
remain historical, and the new fingerprint requires fresh G2/G3 attempts.
Republish is rejected after successful design gates, leaving DESIGN, or
entering execution. G2/G3 PASS is valid only for those current published
artifacts and registered PASS reviews.

For a legacy nonterminal run whose current intent is already authoritative but
whose ledger has no structured requirements/criteria, do not edit JSON and do
not weaken `ticket.criterion_refs`. Read `references/ledger.md`, construct or
use the explicitly authorized `requirements_manifest`, and run
`adopt-requirements` (`publish-requirements`). The manifest must bind the exact
intent revision/document/hash and owner epoch. This migration publication is
hash-addressed, atomic, idempotent for the same bytes, and recorded in
`runtime_provenance`; conflicting records or bytes block.

For a legacy nonterminal run with fresh, ingested PASS coverage and plan
reviews for the current design publication but active historical
`review_finding` issues, do not edit JSON or replay reviews. Run
`migrate-review-currentness` with the current owner token and ledger revision.
It follows durable attempt/review → subject revision/fingerprint → publication
history lineage. Record names and unversioned `affected_refs` are never proof.
Only unambiguously superseded chains receive invalidation/provenance metadata;
current, missing, or ambiguous lineage stays blocking. An already applied
migration is a semantic no-op.

Before a worker/reviewer publishes its final return, run the read-only
`validate-return` against the registered attempt. Structural validation alone
does not establish ingestability. Preserve packet `source_revision` as its
registration revision; publication/subject and attempt-created revisions are
separate recorded bindings. Mixed coverage and plan verdicts are not reviewer
disagreement.

`await_worker_return` and `await_review_return` are internal orchestration
actions, not user checkpoints. After native dispatch, keep the orchestration
turn open for the exact registered attempt, using runtime wait primitives in
bounded intervals. Three consecutive waits of at most 60 seconds with no
observable progress trigger handle/inbox/liveness reconciliation; they never
trigger a request for routine user confirmation. On a matching return, run
`validate-return`, ingest it, and continue the ticket loop in the same turn.
On timeout or a lost handle, stop or interrupt the producer, establish stop
evidence, and use `terminate-attempt` with a released lease only when stopped
is proven, otherwise a quarantined lease. Only an explicit authority-sensitive
blocker or manual-review protocol may become a user checkpoint.

When an ingested repair return is exactly `BLOCKED` before its first write,
has `files=[]`, has no candidate, retains its active lease, and the checkout is
still the exact clean Git base, use `close-blocked-attempt` (alias
`restore-last-validated-candidate`). Do not name or edit a prior candidate.
The command derives and revalidates the immediately preceding same-ticket
candidate, preserves the blocked attempt/return, records the closure receipt,
releases the lease, and restores ticket linkage. Then enter the next ordinary
repair only through a fresh `authorize-repair` decision. That authorization
must already name the exact current same-ticket `source_attempt_ref` whenever
the repaired candidate requires create-to-modify provenance; do not enter
READY first and add the field only to the worker packet. An unused older READY
authorization missing this now-required source may be superseded with a fresh
authorization, preserving and invalidating the prior decision rather than
editing history.

For an already quarantined legacy repair return, do not edit the ledger or
lease. The only normal reconciliation path is
`reconcile-quarantined-attempt`, and only for the exact same-ticket
`create → candidate → repair modify` compatibility case. Supply the exact
ticket/current attempt, named prior create attempt, accepted blocking finding,
candidate/base SHA, actor, and unique reconciliation ID. New repairs may
continue the same ticket through any number of candidate-bound modify repairs
only when every base/candidate edge, finding authorization, and path-specific
lineage is revalidated back to that original create; the current attempt stores
the complete chain. Optionally supply a
pre-attempt baseline; otherwise the command derives it from the exact Git base
tree. The command reruns the checkout audit and publishes the receipt atomically;
all other quarantines remain blocking.

## Read-only dashboard

`tools/dashboard.py` serves a local read-only projection of the selected current `.autopilot/runs/<run-id>/ledger.json`. It reloads that ledger on refresh/auto-refresh, exposes no state mutation endpoint, and does not create a second state store. Missing ledger facts are shown as `CONCERN`; lifecycle, routing, contracts, safety, Git, and G0–G6 remain authoritative.

Read only the route needed for this invocation:

- New run or environment recheck: `phases/start.md`.
- Intent or amendment: `phases/intent.md`.
- Design/G2: `phases/design.md`; plan/G3: `phases/plan.md`.
- Execution, candidate, repair, routine review, and G4: `phases/execute.md`.
- Pause, resume, cancellation, lost handles, or uncertain effects: `phases/recover.md`.
- Verify/G5, manual critical review, import, acceptance, and G6: `phases/accept.md`.

Read `references/ledger.md` before the first state mutation or any recovery question, `references/safety.md` before a project or Git effect, and `references/routing.md` when classifying a task or failure. New workers read `contracts/worker.md`; every reviewer reads the applicable heading in `contracts/reviewer.md`.

## Hard guards

1. Resolve the exact canonical `.autopilot` root and current owner epoch from the ledger. Never select state by nearest directory or by chat memory.
2. Persist a valid prepared attempt before dispatch. A return is evidence, not a commit or integration receipt.
3. Product writes belong to a worker lease. Audit the actual tracked, untracked, relevant ignored, type, rename, and symlink effects before candidate commit.
4. Candidate Git commit precedes review. `INTEGRATED` requires the required independent PASS and a post-review integrity barrier.
5. Final G5 is a fresh current-intent check. For V1 critical axes and every G5 round, use the user-assisted clean-input/session protocol in `phases/accept.md` and `references/safety.md`; setup/context receipts, exact structured return, and integrity checks are mandatory. User approval alone is never G5.
6. Unknown authority, oracle, liveness, schema, or declared input-boundary evidence blocks only the dependent action and records an exact next action. Unobservable underlying host properties are residual trust, not silently promoted to `STRICT_FRESH`; never fill missing evidence with a green default.
7. Materialize readiness with `ready-ticket`; dependencies must be current reviewed `INTEGRATED` outcomes. Enter repair only through `authorize-repair`. Close a no-write BLOCKED repair through `close-blocked-attempt`; close a lost/interrupted attempt through `terminate-attempt` with stop evidence and a released or quarantined lease.
8. Never hand-release quarantine. `reconcile-quarantined-attempt` may restore
   candidate authority only for its fully proven, single-use compatibility
   case and must leave every failed proof unchanged.

After compaction, resume, owner transfer, or doubt about the retained protocol, reread this entry, obtain a fresh `brief`, reread the current phase and its safety/recovery pointers, and only then perform a state-changing action. The summary and old conversation are hints, not authority.

## Completion

Choose exactly one route from the actual `phase × control`, leave `next_action` durable, and report the concrete result. Status-only inspection does not mutate product. A release claim additionally requires the repository qualification suite, including the offline terminal-ACCEPTED lifecycle fixture; unit tests alone are insufficient.
