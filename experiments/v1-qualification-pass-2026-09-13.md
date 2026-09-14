# V1 qualification pass — 2026-09-13

## Scope and execution

This is one resumable qualification pass for the remaining mandatory V1
experiments. It uses the current production snapshot after the existing
targeted fixes:

- `tools/ledger.py`
- `schemas/contracts.schema.json`
- the current lifecycle/contracts/safety files

The black-box harness is [v1_qualification_harness.py](v1_qualification_harness.py).
Raw observations are separated in
[raw/v1-qualification-pass-2026-09-13.md](raw/v1-qualification-pass-2026-09-13.md).
All fixture state was disposable and created under
`/private/tmp/codex-autopilot-v1-qualification-20260913/`.

Explicit exclusions: E03-M was not repeated because its final PASS already
exists; E10 was not run; no global installation was performed.

## Results

| Experiment | Result | Basis |
|---|---|---|
| E01 | **FAIL** | Publication/fencing/view happy paths work, but corrupt-current recovery, effect reconciliation, pinned snapshots, and retention are not available through the helper. |
| E04b | **FAIL** | Foreign tracked/untracked/symlink dirt is detected, but ignored output is omitted and effect/cancel/reconcile safeguards are not implemented. |
| E05 | **FAIL** | `adequacy=REJECTED` route still dispatches; cause-first/no-progress/repair routing is not enforced. |
| E06 | **FAIL** | Empty-coverage PASS review without context evidence integrates; review topology and critical-axis guards are not enforced. |
| E07 | **FAIL** | Manual handoff/import works in the narrow fixture, but a BLOCKED worker can become a candidate and cancellation bypasses stop/reuse reconciliation. |
| E08 | **FAIL** | Cycle/top-level/inbox guards work, but nested contract completeness and several stale/drift/authority/adjudication cases can pass or have no typed gate. |
| E09 | **BLOCKED** | The required economy/compaction run cannot execute against the current package: no orchestrator compaction/restart/usage trace exists. Unavailable token metrics remain UNKNOWN, not green. |

## Findings

### Local implementation defects

1. `audit-write-set` uses default Git status and therefore does not include
   relevant ignored paths in the actual write-set audit.
2. `candidate` does not inspect the ingested worker return and accepts a
   `BLOCKED` return when the Git receipt is PASS.
3. `integrate` accepts a reviewer PASS without required coverage/checks/context
   evidence.
4. The effective nested return schema does not require per-check/per-criterion
   fields, so empty worker verification can validate.
5. The gate surface permits direct `CANCELLED` publication without the stop
   guard/reconciliation contract.

These were recorded, not patched during this pass. They cross multiple
contracts and lifecycle transitions; a safe correction needs a separately
scoped implementation/test pass, not an ad hoc qualification edit.

### Architecture/design blockers

1. There is no implemented operation journal/reconciliation surface for
   prepared effects or crash-after-receipt recovery.
2. There is no implemented orchestrator runtime that can run the required
   6–10-ticket forced-compaction/restart scenario or publish attributable
   economy metrics.
3. E05/E06 cause routing and review-topology decisions exist in design
   contracts but are not represented as enforceable runtime gates in the
   current helper surface.

## Targeted fixes made

None during this pass. The harness is test-only and does not modify production
files. Existing production snapshot hashes and verification are recorded in
the raw artifact.

## Release blockers and verdict

Release blockers remain: E01, E04b, E05, E06, E07, E08 failed required guards,
and E09 is blocked/unmeasurable. Therefore the package is not ready for V1
release or global installation.

**Final verdict: `V1 RELEASE BLOCKED`**

