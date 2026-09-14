# E03-M resumable fixture

This directory is a disposable qualification run for the user-assisted
critical/G5 fallback. The seed repository is intentionally tiny: the worker
changes `VALUE=41` to `VALUE=42`, and the independent reviewer must verify the
current-intent criterion from a pristine export.

The production path is exercised with `tools/ledger.py` commands. The fixture
bootstrap only seeds the already-agreed intent/criteria/ticket metadata needed
to reach the production dispatch/candidate/handoff path; it does not replace
any production implementation or reviewer/import logic.

