# Changelog

## [v1.1.0] — 2026-09-19

Durable lifecycle hardening and qualification release.

- Added immutable storage publication, a semantic writer floor, canonical
  candidate/finding/action projections, shared transition admission, bounded
  repair plans, generalized attempt finalization, typed effects, and shared
  hash-bound candidate proofs.
- Unified accepted review facts and qualification-ref integration, including
  critical/manual purpose separation and fresh final-G5 repair waves.
- Added append-only legacy R58 assessment, normalization, Review05 recovery,
  and copy-only rehearsal without touching live Idea Scout state.
- Separated runtime registration, reservation, and liveness; added immutable
  runtime observations plus exclusive repository/successor ownership.
- Implemented and passed the canonical Q01–Q42 matrix, durable-boundary fault
  injection, same-byte/conflicting replay coverage, reproducible source/test/
  fixture parity, and an independent final reliability review.
- Native process supervision remains explicitly `UNSUPPORTED` and
  adapter-bound; the qualified fake-runtime protocol cannot stand in for a
  native observation receipt.

## [v1.0.11] — 2026-09-17

Audited BLOCKED/HANDOFF continuation candidate patch release.

- Added owner-authorized `preserve-blocked-candidate` for non-empty BLOCKED or
  HANDOFF returns with passing focused checks, typed external/out-of-scope
  blockers, valid ticket lease/provenance, and a passing complete write-set
  audit against the exact Git base.
- Stored the exact audited paths, candidate/base/tree fingerprints, blocker,
  return, authorization, repair provenance, and commit receipt in immutable
  objects and decisions while retaining the BLOCKED verdict and blocker.
- Allowed continuation candidates to receive independent review or serve as a
  later authorized repair base; prohibited their direct integration.
- Rejected failed in-scope checks, missing/stale provenance, quarantined or
  mismatched leases, incomplete/empty audits, and any changed path outside the
  authorized lease without publishing a ledger revision.
- Added positive and negative lifecycle regression coverage, including
  transitive create-to-modify provenance and the current external suite-blocker
  shape.

## [v1.0.10] — 2026-09-17

Repair authorization provenance patch release.

- Moved transitive same-ticket create-to-modify source validation into
  `authorize-repair`, before the ticket can enter `READY`.
- Required the exact current worker or candidate-bound finding review as
  `source_attempt_ref` when the current candidate crosses a create-only zone;
  missing, stale, and foreign sources leave the ledger unchanged.
- Preserved exact authorized-contract matching at dispatch and kept ordinary
  modify repairs source-optional.
- Added a narrow history-preserving supersession path for an unused older
  `READY` authorization whose bound contract lacks the now-required source.
- Added regression coverage for rejection, successful authorize-to-dispatch,
  ordinary repairs, stale sources, and revision-49-style authorization
  recovery.

## [v1.0.9] — 2026-09-17

BLOCKED no-write repair closure patch release.

- Added owner/revision-fenced `close-blocked-attempt` with
  `restore-last-validated-candidate` as an alias for returned BLOCKED repair
  attempts that stopped before their first write.
- Required a schema-valid exact return with `files=[]`, null candidate fields,
  active lease, no unresolved effect, exact checkout HEAD/tree, and a complete
  zero-change Git audit including tracked, untracked, ignored, mode/type,
  rename, and symlink evidence.
- Derived the immediate prior validated same-ticket candidate without accepting
  a candidate selector, released only the blocked attempt lease, preserved all
  attempt/return history, and appended a hash-addressed receipt plus decision
  and evidence records before restoring ticket linkage.
- Added positive/idempotent/follow-on repair-cycle coverage and negative tests
  for wrong status, candidate presence, stale linkage, released lease, and a
  dirty checkout.

## [v1.0.8] — 2026-09-17

Transitive repair provenance patch release.

- Extended the narrow same-ticket create-to-modify exception across continuous
  `candidate → repair modify → candidate` chains without widening create-only
  ticket zones.
- Revalidated every candidate/base edge, worker return, finding-bound review,
  consumed authorization, path, packet allow/deny boundary, and the original
  validated create; stale/forked, foreign, discontinuous, and originless chains
  remain blocked.
- Persisted the complete path-specific attempt/finding/authorization lineage in
  each new repair lease provenance record.
- Added regression coverage for two and many repairs plus stale/forked,
  foreign-path/ticket, and missing-origin failures.

## [v1.0.7] — 2026-09-17

Quarantine reconciliation patch release.

- Added owner/revision-fenced `reconcile-quarantined-attempt` for the narrow
  legacy same-ticket `create → candidate → repair modify` lease mismatch.
- Bound reconciliation to the exact current ticket/attempt, prior DONE create
  return, accepted blocking finding and authorization, candidate/base/HEAD,
  packet allow/deny scope, and complete actual write-set audit.
- Stored the baseline and actor-attributed reconciliation receipt by SHA-256,
  made exact retries zero-effect, and restored candidate authority only after
  every proof succeeds.
- Kept stale bases, foreign/overdeclared paths, non-write-set quarantine,
  missing provenance, unsafe types/symlinks, deny-list escapes, and all other
  quarantined attempts blocked; added positive/idempotent and negative tests.

## [v1.0.6] — 2026-09-17

Lifecycle repair patch release.

- Rejected self-produced contracts in `ticket.contract_refs` during design
  publication and G2/G3 advancement while preserving `ready-ticket` active
  input checks and leaving proposed contracts inactive.
- Defined worker/reviewer waits as bounded internal orchestration actions;
  successful worker ingest now advances to write-set audit/candidate work, and
  lost/timeout recovery retains stop-evidence and quarantine requirements.
- Derived worker leases from the packet allowlist and added an auditable,
  candidate-bound exception for exact same-ticket
  `create → candidate → repair modify` paths. Stale bases, foreign paths,
  missing provenance, packet escapes, and quarantined sources remain blocked.
- Added positive and negative lifecycle regression coverage for all three
  repaired scenarios.

## [v1.0.5] — 2026-09-16

Review-currentness and legacy-ledger migration patch release.

- Added owner/revision-fenced `migrate-review-currentness` for legacy active
  `review_finding` blockers after fresh current G2 coverage and G3 plan PASS
  returns are registered and ingested.
- Added canonical lineage resolution through attempt/review records, subject
  refs/revisions/fingerprints, return-object bindings, and immutable design
  publication history; names and legacy `affected_refs` are never sufficient
  evidence.
- Preserved issue, finding, review, attempt, evidence, publication, verdict,
  and return content while adding only currentness/invalidation and hash-bound
  migration provenance. Missing, conflicting, or ambiguous lineage remains a
  current blocker with an exact reported reason.
- Made exact migration retries semantic no-ops and tightened current G2/G3
  PASS selection against invalidated reviews.
- Corrected status, brief, and dashboard currentness coverage with a
  sanitized revision-77 V12 regression fixture, negative lineage cases, gate
  transition checks, lifecycle qualification, and legacy compatibility tests.

## [v1.0.4] — 2026-09-16

Verified lifecycle-completeness patch release.

- Added atomic, hash-addressed, owner/epoch/revision-fenced
  `adopt-requirements` (`publish-requirements`) for explicit requirements and
  criteria manifests. Legacy v1.0.0–v1.0.3 runs can now publish non-empty
  `ticket.criterion_refs` without editing their ledger or prepared bundle.
- Split packet registration, immutable subject, attempt creation, and return
  source revisions. Added read-only `validate-return` state-bound preflight;
  ingest now applies the same packet/attempt/subject/axis rules.
- Made exact retries zero-effect for requirements/design publication,
  dispatch, return ingest, prepared effects, candidate recording, and effect
  reconciliation; conflicting retries remain rejected.
- Released reviewer leases atomically on every accepted verdict, added
  explicit LOST/INTERRUPTED attempt termination, ticket readiness, and
  cause-bound repair authorization.
- Scoped disagreement to the same review kind and mandate. Supersession now
  fences the transitive review/finding/issue/evidence closure and preserves it
  as immutable historical evidence.
- Tightened G2–G6, ticket dependency, candidate/integration, and terminal
  guards; stale fingerprints, unresolved effects, leases, or blockers cannot
  satisfy a current gate.
- Added durable runtime provenance without rewriting creation provenance:
  creation version, schema version, last mutating helper, compatibility floor,
  and applied migration IDs.
- Added read-only unknown-schema diagnosis, corrected dashboard currentness,
  a machine-readable lifecycle model with mutation/reachability tests, an
  offline terminal-ACCEPTED qualification, and an exact Idea Scout V5 dry run.

## [v1.0.3] — 2026-09-16

Patch release for the iterative immutable design-review lifecycle.

- Added append-only `design_publication_history` with current-publication
  projection and `supersedes`/consumer fencing metadata.
- Added the bounded BLOCK/UNVERIFIABLE DESIGN repair cycle, including PLAN →
  DESIGN recovery, released-lease checks, fresh-review requirements, and
  stale-review gate isolation.
- Preserved v1.0.2 single-publication ledgers, orphan adoption, amendment
  invalidation, and same-byte idempotent recovery.
- Added synthetic V2 → BLOCK → V3 qualification coverage.

## [v1.0.2] — 2026-09-16

Patch release for the post-G1 design publication/reviewer-registration gap.

- Added atomic `publish-design-bundle` (`publish-design` alias) for the
  complete design/interfaces/manifest/plan/tickets/routes bundle.
- Added current-intent, owner/epoch/revision, artifact hash/path, retry,
  conflict, amendment-invalidation, and G2/G3 precondition guards.
- Added durable `prepare-design-review` coverage/plan attempts with reviewer
  identity, role, artifact/version targets, and publication revision binding.
- Preserved v1.0.0/v1.0.1 optional-field compatibility and recovery semantics.

## [v1.0.1] — 2026-09-16

Patch release for the first-intent bootstrap gap found during an Idea Scout V2
production run.

- Added the single-use, owner/revision-fenced `publish-intent` command.
- Made initial intent publication validate the complete proposed ledger before
  installing immutable Markdown, reject conflicting/second publications, and
  safely resume a same-byte document left by interruption.
- Preserved legacy-ledger defaults and the existing `amend`, gate, recovery,
  review, and acceptance semantics.
- Added regression coverage for the real init-to-intent path and its failure
  and recovery cases.

## [v1.0.0] — 2026-09-14

Frozen V1 release of `codex-autopilot`.

### Included

- Codex-native scoped lifecycle with durable ledger, bounded workers,
  independent review, controlled Git effects, and pause/resume recovery.
- Durable `semi`/`full` interaction and `normal`/`deep` depth presets, with
  default `semi + normal`.
- Read-only local ledger dashboard.
- Latest real-world remediation fixes, durable preset coverage, and the
  40-ticket scale qualification fixture in the frozen baseline.

### Verification

- Full regression suite: `28/28 PASS`.
- 40-ticket qualification: `PASS` with schema round-trip, dependency DAG,
  repair, pause, recovery, and terminal acceptance coverage.
- Production helper/dashboard compile and package/reference smoke checks:
  `PASS`.

### Known limitations

- Critical/G5 review uses the qualified user-assisted clean-session route;
  strict automatic reviewer isolation is not qualified.
- V1 remains serial by default; E10 bounded parallel worktrees is post-V1.
- Usage tokens can be unavailable and are reported as unknown/null.
