# Changelog

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
