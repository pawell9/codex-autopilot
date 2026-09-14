# Intent and G1

Read `phases/start.md` first for a new run and `references/ledger.md` before publication. This phase is the authority boundary: canonical Markdown carries exact prose; the ledger carries refs, versions, hashes, statuses, and decisions.

## Build the current intent

Extract the user's current wording without silently normalizing away sources, edge cases, UX requirements, constraints, or exclusions. Record each active requirement with immutable ID, provenance pointer, current revision, and one or more observable criteria. Each criterion names an oracle owner, expected behavior, evidence shape, and whether it is live, negative, edge, or deterministic. Keep `deferred` and `dropped` items explicit with authority; absence is not a scope decision.

Read relevant prior accepted reports, contracts, and decisions as read-only successor context. Current user intent outranks prior memory. If a prior artifact is missing or its hash drifts, record UNKNOWN and resolve the gap; do not reconstruct it from chat or rewrite project instructions.

Material ambiguity is a decision, not an implementation preference. Ask only when authority, product semantics, destructive/external effect, overlapping user changes, scope reduction, or a required oracle has more than one materially different outcome. Store the decision, evidence, affected IDs, introduced revision, and superseded refs. Reversible technical choices stay with the orchestrator and are not ritual approvals.

## Amendments

An amendment creates a new canonical intent Markdown revision before updating ledger references. Preserve exact before/after product wording, user authority provenance, affected requirements/criteria/contracts, and invalidated gates. Quiesce affected work first. Old packets, returns, reviews, and integrated outcomes become historical evidence/STALE; they never silently satisfy the new intent. A terminal run amendment creates a successor run.

## G1 checklist

- Every user requirement is present exactly once or is explicitly deferred/dropped with authority.
- Every active requirement has observable criteria, exclusions, provenance, and an oracle owner.
- Current revisions and Markdown hashes are valid; edited referenced docs are treated as proposed input until adjudicated.
- Scope, user decisions, unresolved questions, risk flags, and requested checkpoints are visible.
- No criterion is weakened to fit existing code or a green but irrelevant suite.

Publish the intent and `next_action` atomically. Then route to DESIGN. If the contract/oracle cannot yet be stated, remain `BLOCKED` with the exact question and owner.

**Done when:** G1 contains the complete current authorized intent, exact criteria, provenance, exclusions, and resolved material ambiguity at one hash-verified revision.
