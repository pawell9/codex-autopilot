# Remediation Wave 1 checkpoint

Date: 2026-09-13 (Europe/Minsk)

Scope completed: adjudicated Wave 1 core correctness/safety only. No E10 and
no full E01/E04b/E05–E09 qualification rerun were executed.

Production changes:

- `tools/ledger.py`: verified corrupt-current recovery from `ledger.prev.json`
  or canonical snapshots; gate/effect/recovery snapshots with eight-entry
  unpinned retention and pinned unresolved/terminal snapshots; prepared effect
  journal plus applied/uncertain reconciliation; QUIESCING cancellation;
  confirmed-route and DONE-only candidate authority; separate review attempt;
  strict review/manual-import matching; fingerprint-based write-set audit.
- `schemas/contracts.schema.json`: closed nested worker/reviewer/acceptance
  identity, check, outcome, finding, packet, receipt, and evidence shapes.
- `tests/test_wave1.py`: focused disposable regression suite.

Verification: `python3 -m unittest discover -s tests -v` passed 8 tests;
`py_compile` and JSON parse checks passed. Frozen E03-M packet, receipts, and
manual import were validated; import replay was run only on a temporary copy.

Resume point: Wave 1 is complete. Remaining adjudicated work belongs to Wave
2 or later: amendment invalidation/consumer closure, durable reviewer
disagreement/adjudication, routing/no-progress, and E09 observability/usage.
