# Final V1 qualification pass — 2026-09-13

> Historical checkpoint. Its `V1 RELEASE BLOCKED` verdict was superseded by
> [the release-state reconciliation](v1-release-ready-reconciliation-2026-09-13.md)
> after the E07 fix, E04b target-mismatch qualification, and E09 PASS.

This pass used the current production helper after the E08 fix. It did not
invoke the global legacy `autopilot` skill, did not run E10, and did not run a
global installation. All effects were confined to disposable temporary roots.

## Package

| Artifact | SHA-256 |
|---|---|
| `tools/ledger.py` | `53c554a4c62765e85885612357e898df8fdb7ae10b0e0f848cc03e8e77b2b431` |
| `schemas/contracts.schema.json` | `e6dbfeca22df65334d6a6e15b4bdbdf66504a13171f0d70d56362e0b70fbdc7c` |
| current qualification runner | `2cbf3fb34495937284c7897ea2927e09b8bff6d9335eda4eca0b6b6aaa1d7667` |

## Results

### E04b

The executed current-surface arms passed:

- dirty tracked/untracked/ignored/symlink audit, including outside-root
  symlink detection;
- partial `BLOCKED` worker return remains non-candidate;
- prepared candidate effect reconciliation and duplicate-effect rejection;
- unexpected post-commit hook mutation is caught by write-set audit;
- disposable `git clean -fd`, `git clean -fdx`, `stash -u`, and `stash --all`
  behavior was observed;
- cancel preserves foreign files, and takeover enters `RECOVERING` with a new
  owner epoch.

The pass stopped before any additional qualification work after the E07
defect below. The wrong-target negative command returned the expected nonzero
result, but in this run it reached the already-applied-operation guard rather
than independently exercising target mismatch; it is not claimed as a
separate target-mismatch oracle here.

### E07

**STOP — new local implementation defect.** The disposable micro-project
advanced through `PREFLIGHT → INTENT → DESIGN → PLAN → EXECUTE`, dispatched a
worker, ingested its return, prepared `OP-E07`, and created the candidate
commit. At that point:

```text
gate --control PAUSED
```

was accepted directly from `ACTIVE`. The resulting ledger had:

- lifecycle control: `PAUSED`;
- attempt `A-E07`: state `RETURNED`, lease `active`;
- operation `OP-E07`: state `prepared`.

Expected behavior is `ACTIVE → QUIESCING`, followed by writer stop and effect
reconciliation evidence, and only then `PAUSED`. The bypass is in
[`tools/ledger.py:1727-1738`](../tools/ledger.py#L1727), where `cmd_gate`
guards direct `CANCELLED` and entry to `QUIESCING` but has no guard for
entering `PAUSED` while attempts or prepared/uncertain operations remain.

This violates the frozen E07 pause/resume contract and the lifecycle control
state machine. The full E07 matrix (repair, amendment, fresh resume, cancel,
manual G5, and G6) was not continued after this finding.

### E09

**NOT RUN.** The stop rule was triggered by the new E07 implementation defect;
no E09 result is invented. Therefore no economy/context/compaction/restart
qualification or token-meter claim is made in this pass.

## Historical checkpoint verdict (superseded)

**`V1 RELEASE BLOCKED` — historical, not current.**

Blocker: direct `ACTIVE → PAUSED` is accepted with live work and an
unreconciled prepared effect. No remediation wave was started.
