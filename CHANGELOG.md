# Changelog

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
