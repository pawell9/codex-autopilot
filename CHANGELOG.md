# Changelog

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
