# Qualification status

**CODEX-AUTOPILOT V1.0.4 — VERIFIED LIFECYCLE PATCH RELEASE.**

Current v1.0.4 evidence: the offline realistic lifecycle reaches revision 48
at `ACCEPT/ACCEPTED`; the exact Idea Scout disposable resume publishes V5 at
revision 31 and registers fresh G2/G3 attempts at revisions 32/33 without
changing the audited source. See `../reports/v1.0.4-qualification.json`.

The frozen baseline includes the latest real-world remediation fixes, durable
presets, and 40-ticket scale qualification. Historical blocked checkpoints
below remain provenance only and do not override the current release state.

## Current release state — 2026-09-13

**Current verdict: `V1.0.0 FROZEN / RELEASE READY`.** See the complete
[release-state reconciliation](v1-release-ready-reconciliation-2026-09-13.md).

| Experiment | Current result |
|---|---|
| E01 | PASS |
| E03-M | PASS — manual G5 roundtrip, lease reconciliation, and G6 `ACCEPTED` |
| E04b | PASS — including the remaining target-mismatch arm |
| E05 | PASS (scoped) |
| E06 | PASS (scoped) |
| E07 | PASS — targeted blocker fixed |
| E08 | PASS |
| E09 | PASS — worker-lease fix, restart/takeover, 6-ticket DAG, usage trace |

The earlier blocked reports below are historical checkpoints superseded by the
targeted fixes and the reconciliation above. `V1 RELEASE BLOCKED` in those
records is not the current verdict. E10 remains post-V1; global installation
is the next authorized action.

Updated: 2026-09-13 (Europe/Minsk)

## Historical pre-reconciliation checkpoint

## Scope and checkpoint

- Authorized sequence: E02 → E03 → E04a only.
- Design and product/research/reference corpus are read-only for this pass.
- Production skill, schema/helper, and runtime implementation are out of scope.
- Initial checkpoint: design/STATUS.md, design/10-decisions-and-experiments.md,
  design/11-review-adjudication.md, normative design/02–07, and re-grounding
  design/08 were read in full before effects.
- Working tree root is not a Git repository. All Git effects will target only
  paths below `experiments/fixtures/e04a/` or an explicitly checked sibling
  disposable path.

## Progress

| Experiment | State | Completed cases | Pending effects |
|---|---|---|---|
| E02 | COMPLETE — PASS with UNKNOWN arms | Context/freshness controls; liveness/interruption; return recovery; route rejection/inheritance evidence | Abrupt process/UI-loss semantics deferred as explicit UNKNOWN; strict final carried to E03 |
| E03 | COMPLETE — FAIL/BLOCKED | Routine native review/export/barrier qualified; persistent tamper and write-restore limit proven; CLI/custom/native-review availability recorded | Requires authenticated restricted clean process or exposed custom/native restricted reviewer for critical/G5 |
| E04a | COMPLETE — PASS | Empty/seed bootstrap; approvals; branch/candidate/repair; denial reconciliation; permitted placement/root/common-dir/source-scan/fallback | Full Codex session-loss persistence remains UNKNOWN; E04b intentionally not run |

## Fixture paths

- E02: `experiments/fixtures/e02/`
- E03: `experiments/fixtures/e03/`
- E04a: `experiments/fixtures/e04a/`
- Denied sibling path: `/Users/pawell_9/Documents/codex-autopilot-e04a-worktree`
  (absent; denial preserved, no bypass).
- Registered permitted sibling:
  `experiments/fixtures/e04a/seed-repo-worktree` on
  `autopilot/e04a-worktree` at `362380f2574af1cd9496b9f3a4e59caa023300b0`.

## Live handles and processes

- Native agents: none live.
- Shell/CLI processes: none.
- Background writers: none known; all bounded E02 traces reached terminal state.

## Exact next action

Stop. Qualification is BLOCKED by E03; implementation is not authorized. The
exact resume condition is an authenticated/exposed automatic reviewer transport
that can be technically restricted from authoritative filesystem/tool effects.
On a new qualification request, reread this STATUS and applicable design rules,
reconcile actual fixtures/liveness, then rerun only the affected E03 restricted
process/custom/native-review arm. Do not repeat E02 or E04a actions blindly.
