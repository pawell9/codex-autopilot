# Final V1 qualification rerun — 2026-09-13

This rerun used the current snapshot after Wave 1 and Wave 2, disposable
fixtures, and the raw observations in
[raw/v1-qualification-rerun-2026-09-13.md](raw/v1-qualification-rerun-2026-09-13.md).

## Result matrix

| Experiment | Observed result | Verdict | Notes |
|---|---|---|---|
| E01 | Recovery, fencing, snapshots, effect/cancel guards PASS | PASS | Disposable run; 8 unpinned snapshots plus pinned recovery snapshot |
| E04b | Core audit/effect/cancel arms PASS | HALTED | Remaining destructive-state arms stopped by E08 rule; old missing `evidence_ref` was TEST FIXTURE defect |
| E05 | Functional route/typed-return/no-progress guards PASS | PASS (scoped) | Comparative tuning is OUT OF V1 on this package surface |
| E06 | Contract completeness, separate review authority, adjudication PASS | PASS (scoped) | Optional frontier comparison is OUT OF V1 |
| E07 | Existing E03-M import/cancel regressions PASS | HALTED | Fresh complete G0–G6 run stopped before completion |
| E08 | Outside-lease worker file claim accepted by `ingest-return` | FAIL | New local implementation defect; no issue/quarantine |
| E09 | Null-token usage handling PASS; compaction/restart qualification unavailable | BLOCKED/UNKNOWN | No shipped orchestrator runtime exposes required trace/compaction/restart |
| E03-M regression | Frozen validation/import/resume PASS | PASS | Full manual roundtrip intentionally not repeated |

## Final verdict

`V1 RELEASE BLOCKED`

Reason: E08 exposed a new local safety/contract implementation defect. Per
the requested stop rule, no remediation wave was started and no further
qualification actions were taken after that observation. E10 and global
installation were not run.
