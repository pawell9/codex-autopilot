# Remediation Wave 2 checkpoint

Date: 2026-09-13 (Europe/Minsk)

Scope completed: State / Routing / Adjudication / Observability remediation
only. Wave 1 semantics remain intact. E10 and the full qualification rerun
were intentionally not run.

Production changes:

- `tools/ledger.py`: full amendment consumer invalidation with durable
  invalidation records; current intent document ref/hash binding checks for
  dispatch and manual G5 handoff/import; dispatch eligibility hard-blocks
  rejected or invalid context/fallback routes; worker BLOCK/FAILED/HANDOFF
  returns and reviewer findings are stored as immutable object refs and
  typed ledger records; reviewer disagreement is blocked until an evidence-
  backed `reviewer_adjudication` decision is published; repair packets carry
  cause/finding/hypothesis/expected proof/stopping condition/causal change;
  identical repair signatures are rejected; `publish-usage` and expanded
  `brief` expose attributable counters, trace, bytes, wall time, manual
  costs, shared setup, G0–G6 costs, and explicit null-token reasons.
- `schemas/contracts.schema.json`: Wave 2 finding, invalidation, repair,
  intent-binding, adjudication, and observability contracts.
- `tools/dashboard.py`: read-only projection includes findings,
  adjudications, and usage data.
- `tests/test_wave2.py`: focused Wave 2 regression coverage.

Verification:

- JSON schema parse: PASS.
- Python compile checks for ledger/dashboard: PASS.
- Wave 2 tests: 6 PASS.
- Wave 1 tests: 8 PASS.
- Combined `python3 -m unittest discover -s tests -v`: 14 PASS.
- E03-M regression/manual import roundtrip: remains PASS through the Wave 1
  test suite.

Resume point: run the separately authorized general qualification rerun when
requested. Do not infer release readiness from this checkpoint alone; the
qualification evidence remains pending by instruction. E10 remains excluded.
