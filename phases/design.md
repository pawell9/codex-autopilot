# Design and G2

Read the current intent and `references/ledger.md`. Write a versioned canonical design document containing the smallest implementation spec, interfaces, assumptions, boundaries, and oracle plan needed by the active criteria. Do not copy the full ledger into prose.

## Design work

Trace every active criterion to a contract or observable behavior, a producer/consumer seam where applicable, and a verification scenario. Name compatibility, migration, security, data-integrity, and integration risks. Keep exact signatures/invariants in the canonical contract section. An assumption is not a fact until its evidence is recorded; an unresolved architecture or oracle choice gets a research mandate or blocking decision.

The plan must anticipate independent evidence beyond worker tests: expected-value checks, live checks where required, negative/mutation checks, and edge/malformed cases. A green suite that can miss a seeded loss or bypass is not a sufficient oracle.

## G2 coverage request

Before design publication, verify that every referenced requirement and
criterion exists as a current structured record. A legacy run with a current
intent but missing these collections must use an explicit, intent-bound
`requirements_manifest` and `adopt-requirements`; never derive records from
prose, remove non-empty `criterion_refs`, or edit the ledger. The resulting
requirements publication becomes part of the design publication binding.

When G1 is complete, publish the complete design-stage bundle before preparing
the reviewer: design, interfaces/contracts, manifest, implementation plan,
tickets, routes, and dependency bindings must all be immutable, hash-verified
documents or ledger records in one `publish-design-bundle` transaction. The
bundle is bound to the current intent revision and owner epoch. A same-byte
retry adopts an orphaned canonical document after a crash; a conflicting byte,
missing source, traversal path, stale revision, or partial bundle leaves the
ledger unchanged. If coverage or plan review returns BLOCK/UNVERIFIABLE, a
nonterminal run may return to DESIGN and publish a new bundle version. The
prior publication remains in append-only `design_publication_history` with its
review evidence and consumer fencing; the new publication becomes current and
requires fresh reviews. No active writer/reviewer lease may remain, and this
repair route is unavailable after successful design gates or execution begins.
The transaction's next action is the only route to G2.

Register the coverage reviewer with `prepare-design-review --review-kind
coverage --reviewer-identity ... --reviewer-role ...`. This durable attempt
records the exact bundle fingerprint, artifact/version refs, publication
revision, intent binding, reviewer identity/role, and PREPARED state before the
reviewer runs. Ingest the exact structured return through the normal review
path; a PASS is then bound to that attempt and target. The packet distinguishes
registration/source revision from immutable subject revision and
attempt-created revision. Run `validate-return --kind review` against the
exact attempt before the reviewer publishes its return. Coverage and plan are
different logical mandates and cannot disagree merely because their verdicts
differ.

Prepare a fresh `coverage` reviewer packet on the current intent and proposed design. It contains no author defense, worker self-rating, or implementation history. The reviewer assesses every active requirement, omissions, silent narrowing, assumptions, interfaces, and oracle feasibility, then returns structured coverage and findings on the exact document revision. A PASS requires all active requirements assessed with no blocking gap.

If the routine reviewer route is unavailable, do not self-review. Record the capability blocker and use the designated recovery/fallback for that action; manual critical/G5 is not a substitute for ordinary design coverage.

## Compact branch

For at most two routine tickets with no public interface change, migration, unresolved semantics, or cross-ticket integration risk, combine design and plan in one canonical artifact while recording separate G2 and G3 outcomes. A later material discovery expands to full depth and invalidates affected gates. Apply the neighbour/payback test only to adjacent micro-changes sharing zone, authority, and dependency boundary.

Publish G2 only against matching intent/spec hashes. A contract defect discovered later returns to this phase or INTENT according to the current transition rules in `phases/intent.md` and `references/ledger.md`; it is never patched silently inside a worker ticket.

**Done when:** the complete bundle is PUBLISHED, an independently registered coverage attempt has returned PASS on its exact fingerprint/revision, every active criterion has a feasible contract and oracle, and assumptions/risks are explicit.
