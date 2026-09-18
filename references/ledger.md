# Ledger and artifact protocol

This is the state authority. JSON stores structured orchestration state; canonical prose/spec/interfaces remain immutable Markdown revisions referenced by path, version, and SHA-256. Generated views are projections. One orchestrator owner writes state through `tools/ledger.py`; workers receive only an exact scratch return grant.

## Namespace and envelope

```text
<control-root>/.autopilot/
├── owner.lock
├── runs/<run-id>/{ledger.json,ledger.prev.json,docs/,snapshots/,objects/,packets/,views/}
└── scratch/<run-id>/<attempt-id>/
```

The control root is the permanent primary checkout recorded by Git inventory. A repository-identity owner registry/lock permits one nonterminal run owner at a time. A run ID is path-safe and exclusive. Existing nonterminal state is recovered, never overwritten; terminal runs are read-only. A changed scope starts in a fresh namespace via `init-successor`, whose typed manifest binds the exact terminal predecessor publication/hash, accepted evidence, scope decision, candidate/resources, explicit exclusions, and unknowns. Attempts, live reservations, repair authorizations, and current pointers are explicitly excluded from carry-forward. `.autopilot/` is excluded only by its exact owned `.git/info/exclude` line when authorized; it is not a backup and may be removed by broad clean/stash/delete operations.

The ledger envelope includes `schema_version`, `run_id`, monotonic `revision`, `previous_publication_hash`, UTC timestamps, `skill_version`, `policy_version`, `repository`, `owner`, optional durable `run_settings`, optional `runtime_provenance`, `lifecycle`, and only the collections needed by the run. `skill_version` remains the run creation version. `runtime_provenance` separately records current schema, last mutating helper, compatibility floor, and hash-bound applied migrations; it is added on the first v1.0.4 mutation and never fabricates unprovable history. `run_settings` contains `interaction_mode` (`semi`/`full`) and `depth` (`normal`/`deep`); missing fields in legacy ledgers resolve to `semi + normal` without an in-place migration. `null` plus a reason means unknown; `[]` means verified absence; missing optional collections mean not applicable. IDs are immutable and references use IDs, never positions. SHA-256 proves stored-byte identity, not claim truth.

Required records are `repository/owner`, `lifecycle.next_action`, `documents/intent`, `requirements/criteria/contracts`, `decisions`, `tickets`, `attempts`, `issues`, `reviews/acceptance`, `operations`, `capabilities/routes`, `evidence`, and `usage` as applicable. Repairs and handoffs are attempt modes/payloads; blockers and concerns are typed issues; waves, ready queues, progress, and transition lists are derived. `INTEGRATED` is a workflow fact, not fulfillment without current evidence.

## Atomic publication

For every mutation, the helper acquires the fixed advisory owner lock, rereads the current ledger, checks owner token/epoch and expected revision, validates the entire proposed snapshot and semantic invariants, and writes the prior valid bytes to `ledger.prev.json`. It then writes a same-directory temporary file, flushes/fsyncs, atomically replaces `ledger.json`, and syncs the directory. If the previous backup fails, no new publication is accepted. Orphan temporary files/objects are harmless and never authority. A same-byte unreferenced initial-intent document may be adopted by a retry after interruption; conflicting bytes block rather than overwrite. Generated view failure does not roll back state.

`ready-ticket` atomically materializes dependency/current-publication readiness. `dispatch` publishes the route, checkout reservation, packet ref/hash, execution binding, and `PREPARED` attempt; it registers a stable spawn request but does not spawn. `terminate-attempt` records LOST/INTERRUPTED plus exact typed runtime stop/not-started evidence and releases or quarantines its reservation. `finalize-attempt` records the total safe disposition for returned non-DONE and terminated worker attempts without inventing a candidate; `reconcile-finalized-attempt` can later release its quarantine only from an exact runtime receipt and a fresh exact-baseline audit. `close-blocked-attempt` remains the narrow no-write BLOCKED repair closure and has the same runtime stop guard. After G1, `adopt-requirements` may publish an explicit legacy requirements/criteria manifest, `migrate-review-currentness` may fence provably superseded legacy findings after fresh current G2/G3 PASS ingestion, and `publish-design-bundle` publishes the complete design bundle. `prepare-design-review` registers coverage or plan identity and immutable subject bindings without spawning. `validate-return` is a read-only state-bound preflight; return/review ingestion releases a reservation only when exact stop/not-started evidence is already valid. `candidate` and `preserve-blocked-candidate` consume the ingested worker return and the exact Git operation receipt through one `VerifiedCandidateProof` finalizer. `authorize-repair` binds one bounded grouped finding set to a canonical `RepairPlan` and packet-bound `AttemptPlan`; dispatch reruns the same preflight and consumes it once. `integrate` accepts exact review evidence and integrity PASS, resolves the authorized repair finding, and publishes current integration. `publish-intent`, `gate`, `amend`, and `recover` are compound intent commands. `diagnose`, `brief`, and `status` are bounded reads.

## Runtime observations and reservation safety

Every runtime-protocol attempt carries a stable `spawn_request_id`, four-way
liveness (`unknown`, `running`, `stopped`, `not_started`), and refs to immutable
observation objects. The execution binding snapshots run/ticket/attempt/epoch,
packet and route, exact checkout/base, intent/design publication, criteria,
and contract bindings. The lease is only a checkout reservation; it does not
assert whether a process is alive.

The external adapter submits a schema-valid receipt with `observe-runtime`
(`--event start|heartbeat|return_observed|stop|not_started`). Its CLI also
requires the current control root, run ID, owner token, revision, attempt ID,
event ID, and event-file path. Every receipt is
bound to the exact run, attempt, epoch, packet hash, spawn request, and runtime
instance, and records observer/build, time, coverage, and a unique event ID.
First valid `start` transitions unknown→running and increments `spawn_calls`
once. Heartbeat confirms an observation of the same running instance but is
not a liveness lease/timeout mechanism. `return_observed` binds the immutable
return hash and does not prove stop. Exact `stop` transitions to stopped only
for the observed instance (or an exact unresolved spawn request) and requires
`coverage.descendant_writers` to be `included`. `not_started` is valid only for a
PREPARED/DISPATCHED request with no start, instance, or runtime return.

Dispatch and review preparation increment `attempt_registrations`, not
`spawn_calls`, and return `register_only_use_spawn_request_id_once`. The
external adapter may spawn only once with that stable ID. An exact registration
replay returns `existing_request_do_not_spawn_again`; exact receipt replay is
zero-effect (`already_observed; do_not_spawn_again` for a start), even after
later progress. Reusing an event ID with different bytes is rejected.
Timeouts, missing heartbeats/handles, worker returns, user attestations, and
negative process scans never transition liveness to stopped. A legacy attempt
without a runtime record remains readable with liveness `unknown`; it gains
no fabricated receipt. Candidate/review qualification and release/reuse
mutations fail closed until exact stop or valid not-started evidence exists.

The helper validates and persists external claims; it does not itself spawn,
supervise, enumerate, or kill native processes. Stop reliability depends on
the adapter and truthfulness/completeness of its descendant coverage. Phase G
implements the deterministic receipt protocol, not native runtime
qualification/conformance.

Candidate effects follow `prepared → applied | uncertain | abandoned`, `uncertain → applied | abandoned`, and `applied → finalized`. `applied` is still unresolved for a candidate commit: it means the physical Git commit is proven but its candidate projection is not yet linked. The derived `adopt_applied_effect` action finalizes that same operation without another commit. Finalization atomically links one immutable receipt, one full write-set audit, one `VerifiedCandidateProof`, the producer attempt, and the candidate projection. The proof binds run/ticket/attempt/operation identity, exact base/direct parent/commit/tree, checkout/target/authority, packet and return objects, candidate quality, and the content-addressed receipt/audit. Exact replay verifies those stored objects and publishes no revision; an abandoned or finalized operation cannot be re-armed under the same ID.

`preserve-blocked-candidate` is the only candidate path for a non-empty
`BLOCKED`/`HANDOFF` worker return. It requires an exact current ticket/attempt,
owner authorization bound to a current typed external/out-of-scope issue and
the immutable return, passing focused checks, explicit attribution of any
external failed checks/criteria, a current non-quarantined reservation with
an exact runtime stop receipt for the returned producer, and valid repair
provenance. It verifies a clean direct commit on the exact base, reruns
the complete checkout write-set audit against the Git base tree, and stores the
receipt, commit receipt, authorization decision, and evidence atomically. It
preserves `BLOCKED`, never accepts an in-scope failed check or lease/audit
failure, and produces a continuation-only candidate that can be reviewed or
used by a later authorized repair but cannot be integrated on its own.

`reconcile-quarantined-attempt` is the sole mutating compatibility path for an
already quarantined returned repair whose legacy lease encoded `create` where
the authorized packet required `modify`. Under the owner lock it proves the
same current ticket/attempt, exact prior same-ticket DONE create return,
current blocking finding and consumed authorization, candidate/base/HEAD,
packet allow/deny scope, and complete actual write set against a supplied
pre-attempt baseline or the exact Git base tree. It stores the baseline and
full generated receipt by SHA-256, names
the actor, invalidates only the matching write-set quarantine issue, and
restores the attempt's packet-scoped candidate authority. The attempt points
to that receipt; an exact retry does not publish another revision. No other
quarantine cause is eligible.

`reconcile-finalized-attempt` is the general proof-carrying release path for a
quarantine already recorded by `finalize-attempt`. It requires the exact
ticket/attempt/finalization receipt, a typed runtime stop/not-started receipt
with descendant-writer coverage, and a fresh Git audit showing HEAD, tree, tracked,
untracked, ignored, type, and symlink state exactly match the verified base or
retained candidate. It resolves only attempt-termination/write-set quarantine
issues, never converts partial work into `DONE`, and makes an initial ticket
`READY` only after disposal to the baseline. Its immutable receipt replays
after later pointer progress; conflicting evidence or any remaining write or
effect leaves quarantine unchanged.

`init` publishes revision 0 without intent. `publish-intent` is the single-use bootstrap transaction: from PREFLIGHT/INTENT and ACTIVE/BLOCKED/RECOVERING it validates non-empty UTF-8 Markdown, owner/revision, destination, complete next ledger, and absence of any prior intent binding before installing immutable bytes and publishing the INTENT revision. Existing blocking issue refs remain blocking; a recovering run remains `RECOVERING` until reconciliation completes. Once intent exists, only `amend` may publish a later intent revision.

`adopt-requirements` is the schema-1.0 compatibility publication for a nonterminal, pre-execution run. Its explicit manifest contains complete requirement↔criterion links and criterion oracles and binds the current intent revision/document/hash and owner epoch. The helper validates uniqueness, cross-links, provenance refs, status, and conflicts; stores exact bytes as `objects/<sha256>`; and atomically appends requirements, criteria, the requirements publication, and a migration record. It never infers prose. An exact retry is zero-effect; same ID with different bytes/records, active leases, prepared effects, stale fencing, or execution entry is rejected.

`migrate-review-currentness` is the schema-1.0 compatibility operation for
legacy design-review blockers that escaped publication supersession fencing.
It requires a nonterminal run, exact owner token and current revision, plus a
fresh registered/ingested PASS pair for both coverage and plan on the current
publication fingerprint and subject revision. For each active blocking
`review_finding`, it follows issue/finding source refs to exact attempts or
reviews, joins attempt/review records through their immutable return object,
and intersects subject ref, subject fingerprint, and subject/target revision
against `design_publication_history`. Attempt, review, issue, or finding names
and legacy `affected_refs` do not prove lineage. A unique current match stays
blocking; a unique superseded/invalidated match receives only
`invalidated_by` currentness metadata across its issue/finding/source/evidence
closure. No content is deleted, adjudicated, or rewritten. Missing,
conflicting, and multiple matches stay blocking and are reported precisely.
The exact report is stored by SHA-256 and referenced from
`runtime_provenance.applied_migrations`. A second run for the same current
publication returns that report without changing the revision, usage, or any
record.

`publish-design-bundle` is the single publication boundary after G1. It requires
DESIGN phase, current intent revision/document hash, all required design-stage
artifact kinds, valid structured contracts/tickets/routes, an acyclic dependency
graph, and regular non-symlink UTF-8 sources with matching hashes. The helper
also treats `ticket.contract_refs` strictly as inputs and
`contract.producer_refs` as output provenance. Their intersection for the same
ticket is rejected before publication and again at G2/G3 for an already
published legacy bundle; it is never repaired by activating a proposed
contract or silently rewriting old bytes. The helper
validates the complete proposed snapshot before installing canonical documents;
the ledger is unchanged on every rejected input. Existing same-byte documents
are adopted, same-byte publication retries are idempotent, and conflicting
bundle/document bytes are never overwritten. `amend` marks the publication and
its consumers invalidated, so old design reviews cannot satisfy the new intent.
After a current coverage or plan review returns BLOCK/UNVERIFIABLE, a
nonterminal DESIGN run may publish a new bundle version when all
owner/epoch/revision/intent and lease fences still match. The old publication
is retained in append-only `design_publication_history` with `SUPERSEDED`
status and consumer refs; the new record is appended and becomes the current
projection. Reviews, findings, and evidence retain their exact historical
fingerprints, while G2/G3 only accept PASS reviews matching the new current
fingerprint. A PLAN review repair may explicitly return to DESIGN while
blocked; republish is rejected after a successful design gate or once
execution has begun.

The helper does not call models, spawn/supervise/kill native agents, hold a daemon loop, parse prose, or make substantive review decisions. It may validate a receipt from an approved native Git operation; it must not bypass approval by becoming an opaque shell wrapper. It also does not own the orchestration turn or runtime wait loop. The skill-level orchestrator treats `await_worker_return` as internal and waits in bounded intervals. `terminate-attempt` records workflow outcome; producer stop is established only by the exact external runtime receipt. A normal matching return advances `next_action` to write-set audit and candidate preparation, but does not release a reservation until stop evidence exists.

## Semantic guards

- Legal run phases are `PREFLIGHT, INTENT, DESIGN, PLAN, EXECUTE, VERIFY, ACCEPT`; controls are `ACTIVE, QUIESCING, PAUSED, BLOCKED, RECOVERING, ACCEPTED, FAILED, CANCELLED`.
- Tickets move `PLANNED → READY → RUNNING → CANDIDATE → REVIEW → INTEGRATED`, with `BLOCKED, REPAIR, STALE, CANCELLED` as local branches. Attempts are `PREPARED, DISPATCHED, RETURNED, LOST, INTERRUPTED`.
- A no-write BLOCKED repair closure is legal only for the exact current
  same-ticket RETURNED worker repair with an active reservation and exact
  runtime stop/not-started evidence, null candidate, schema-valid BLOCKED
  `files=[]` return, no unresolved effect, and a clean
  checkout whose HEAD/tree equal the immediate prior validated DONE candidate.
  The command has no candidate argument, so it cannot select an arbitrary old
  candidate. It appends receipt/decision/evidence, changes only the reservation and
  ticket linkage projections, and leaves every attempt and return in history.
- Only legal phase/control transitions are accepted. `ACCEPTED` requires a G5 PASS and G6 record. An amendment stales affected evidence; it does not reuse old acceptance.
- Ticket dependencies must be current reviewed `INTEGRATED` outcomes. DAG validation rejects cycles. Active/quarantined reservations and stale epochs cannot be reused; missing runtime records remain unknown and never bypass the exact stop/not-started gate.
- A return is accepted only when attempt, packet hash, contract versions, owner epoch, subject fingerprint, and lease match. Late/stale payloads remain evidence without authority.
- Worker leases are the normalized packet write allowlist, not the whole ticket
  zone. Repair may add `modify` only for an exact path that the named same-ticket
  source attempt declared as `create`, when its candidate SHA equals the repair
  packet base and the authorized finding is bound to that candidate. The
  authorization stores the exact repair-contract object and is single-use.
  `authorize-repair` validates required transitive create-to-modify provenance
  before READY, including the current same-ticket source attempt. Missing,
  stale, or foreign sources publish no state change. The authorization and
  lease derivation are stored on the repair attempt. Legacy unbound
  authorizations require an explicit `authorize-repair` rebind and are never
  inferred. An unused older READY authorization whose exact bound contract
  lacks a now-required source may likewise be superseded; the old decision is
  retained with `invalidated_by` and exact dispatch matching is unchanged. The
  narrow reconciliation command above may repair only the
  already-recorded create-only compatibility mismatch; all other zone
  violations retain the existing quarantine path.
- Packet registration revision, immutable subject/publication revision,
  attempt-created revision, return source revision, and ingest-time current
  revision are separate facts. Return `source_revision` must equal the packet
  registration binding, not an older publication revision. `validate-return`
  and ingest share this rule and exact packet axes.
- Reviewer disagreement requires the same current subject, review kind,
  mandate, and target revision. Coverage PASS plus plan BLOCK is an ordinary
  mixed outcome. Supersession fences the transitive attempt/review/finding/
  issue/evidence closure; old records remain immutable but advisory.
- A prepared effect with unknown result becomes `uncertain` and is reconciled by fresh identity/base/tree/target/authority receipt evidence before any repeat. A proven candidate commit becomes `applied` and must be adopted/finalized from its immutable receipt without repeating Git. No exactly-once promise exists.
- G2/G3 gate PASS requires a current `PUBLISHED` design bundle and matching
  non-invalidated PASS coverage/plan review records; provisional, historical,
  invalidated, or unpublished artifacts never satisfy either gate.

## Objects, docs, views, and inboxes

Copy validated returns, manifests, receipts, and review evidence into immutable `objects/<sha256>` before referencing them. Keep exact source bytes. Canonical Markdown amendments are written as new versions first; a user-edited referenced file causes hash mismatch and dependent gates stop until authority is adjudicated. Views carry run ID/source revision/hash/generated marker and can be regenerated.

An attempt inbox is exact, regular, non-symlink, bounded, and registered before dispatch. The producer writes a sibling temp file, flushes/closes it, and atomically renames to `return.json`; the producer then stops writing. Ingest rejects traversal, escape, symlink, size overflow, inconsistent bytes, conflicting duplicate hashes, and malformed/stale subjects. Same-hash duplicate ingestion is idempotent. Crash after rename may be imported after stop, integrity, and version checks without rerunning the agent.

## Recovery and retention

`ledger.prev.json` is the last valid publication. Recovery snapshots are selected copies at gates and before dangerous effects; retain the last eight unpinned snapshots plus pinned unresolved-operation/recovery/terminal-acceptance snapshots. Never prune referenced evidence/docs/packets or unresolved receipts, and never prune during corrupt-state diagnosis.

Owner takeover and checkout reuse are separate. Planned handoff or explicit user attestation may authorize a new orchestration owner/epoch; neither attestation, epoch change, nor corroborating process scans proves producer stop. Keep checkout reservations quarantined until the exact attempt-bound runtime stop/not-started receipt passes validation and the checkout audit succeeds. The helper records the external receipt but cannot itself stop native processes or prove that the adapter enumerated every descendant; receipt coverage is an explicit trust boundary. Then audit actual state, invalidate affected facts/gates, and publish the earliest safe next action. A crash after design documents are installed but before the ledger publication leaves only an orphan; resume retries the same bundle and adopts same bytes or reports a conflict. A crash after a revised publication commits but the response is lost, retrying the exact same bytes adopts the current publication without appending duplicate history. A crash after publication but before reviewer registration leaves a valid published bundle with the durable `prepare_g2_coverage_review` next action; resume registers the review against that exact revision. An unknown schema is diagnosed read-only through `diagnose`; no fallback writer may publish against it.

**Completion:** each publication is lock-protected, revision/epoch-checked, schema/semantic-valid, atomically durable, and reconstructible from files plus Git; every uncertain effect has a quarantine/next action rather than a duplicate execution.
