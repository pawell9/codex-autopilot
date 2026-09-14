# Design and G2

Read the current intent and `references/ledger.md`. Write a versioned canonical design document containing the smallest implementation spec, interfaces, assumptions, boundaries, and oracle plan needed by the active criteria. Do not copy the full ledger into prose.

## Design work

Trace every active criterion to a contract or observable behavior, a producer/consumer seam where applicable, and a verification scenario. Name compatibility, migration, security, data-integrity, and integration risks. Keep exact signatures/invariants in the canonical contract section. An assumption is not a fact until its evidence is recorded; an unresolved architecture or oracle choice gets a research mandate or blocking decision.

The plan must anticipate independent evidence beyond worker tests: expected-value checks, live checks where required, negative/mutation checks, and edge/malformed cases. A green suite that can miss a seeded loss or bypass is not a sufficient oracle.

## G2 coverage request

Prepare a fresh `coverage` reviewer packet on the current intent and proposed design. It contains no author defense, worker self-rating, or implementation history. The reviewer assesses every active requirement, omissions, silent narrowing, assumptions, interfaces, and oracle feasibility, then returns structured coverage and findings on the exact document revision. A PASS requires all active requirements assessed with no blocking gap.

If the routine reviewer route is unavailable, do not self-review. Record the capability blocker and use the designated recovery/fallback for that action; manual critical/G5 is not a substitute for ordinary design coverage.

## Compact branch

For at most two routine tickets with no public interface change, migration, unresolved semantics, or cross-ticket integration risk, combine design and plan in one canonical artifact while recording separate G2 and G3 outcomes. A later material discovery expands to full depth and invalidates affected gates. Apply the neighbour/payback test only to adjacent micro-changes sharing zone, authority, and dependency boundary.

Publish G2 only against matching intent/spec hashes. A contract defect discovered later returns to this phase or INTENT according to the current transition rules in `phases/intent.md` and `references/ledger.md`; it is never patched silently inside a worker ticket.

**Done when:** an independent fresh coverage verdict is PASS on the exact intent/design revision, every active criterion has a feasible contract and oracle, and assumptions/risks are explicit.
