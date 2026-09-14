# Routing and cause-first escalation

Routing first selects the required capability, then a currently available resource. Runtime model/effort catalogs are capability facts, not this file. Never infer adequacy from a slug, UI label, or API price.

## Assessment

Complexity is `bounded` (known local pattern), `coupled` (interdependent interfaces/debugging), or `ambiguous` (conflicting contract/oracle or unknown causality). Consequence risk is `routine` (local/reversible), `elevated` (public interface, data correctness, multiple consumers, critical UX), or `critical` (security/trust, data loss/migration, weak rollback, irreversible effect). Unknown risk is elevated; uncertain destructive effect is critical. Plan risk is at least every ticket and integration risk.

Capability classes are `routine`, `implementation`, `deep`, and optional `frontier`; reasoning bands are `light`, `standard`, `deep`, `exceptional`. They are independent dimensions and do not imply a 4×4 model table. Default routine implementation is `implementation/standard`; coupled/elevated work uses `deep/deep`; critical review uses a deep fresh reviewer plus an independent risk axis. Sparse effective bindings are recorded only when discovered and adequate.

## Resolve each attempt

1. Derive capability, band, risk, cause, oracle, and user/project restrictions from the current packet.
2. Use only valid facts: exposed options, accepted spawn resolution, inherited route with evidence, context grade, permission surface, and relevant fingerprint.
3. Pick the least costly known adequate route; when comparative cost is unknown, use the validated default. Do not scrape credentials or invent token/credit prices.
4. If an override is unknown/rejected, use an adequate inherited route only with an evidence-backed inheritance chain. Otherwise use one bounded qualification/decomposition step; persistent adequacy uncertainty blocks the dependent action rather than causing endless decomposition.
5. On native rejection, record the binding failure and determine whether spawn happened. Unknown spawn state enters recovery; it is never duplicated.
6. Persist requested versus observed resolution, route assessment, fallback cause, and packet before dispatch.

Fallback is validated same-class route → adequate inherited route → smaller bounded decomposition with the same outcome → precise capability blocker. Frontier is optional; deep fresh evidence and a stronger oracle may resolve the issue.

## Cause-first triage

`implementation` gets reproduction, a minimal repair, and regression proof. `contract`/`user_intent` gets an orchestrator amendment and affected gates. `oracle` gets an independently reconstructed expected outcome. `environment`/`permission` gets a conditional probe or user action, never a model upgrade or bypass. `ownership` quarantines the exact write set/base. `orchestration` gets ledger/attempt/effect reconciliation. `unknown` gets a fresh read-only diagnosis.

Safe retry repeats an operation only after a confirmed transient cause and reconciliation. Repair changes the solution and records finding, cause, hypothesis, expected new proof, and stopping condition. A repeat requires a causal change in input, approach, capability, or evidence. Repeated same-class failure first creates a diagnostic checkpoint; no magic repair ceiling or automatic success exists. Fresh context is required after intent/contract/zone amendment, lost/context-saturated worker, or repeated causal defect after substantive repair. A same live worker is allowed only for one local unambiguous omission under an unchanged contract and still receives a new attempt identity.

De-escalation occurs only on a new attempt after the contract is stable and the pattern is evidenced; it never weakens oracle or independence. Conflicting reviewers are preserved separately: duplicate only identical claims, reproduce factual disagreement, amend contract for ambiguity, and treat preference outside intent as advisory. Majority vote and a stronger model do not replace evidence.

External/frontier review is optional and requires explicit authority for a new service/cost scope. No external provider, Claude bridge, Astra, or reviewer name is a V1 dependency. Native availability does not waive critical axes or G5.

Usage fields store observed calls, time, bytes, approvals, and tokens when available; unavailable meters are `null` with reason. The happy-path bookkeeping target is at most four model-invoked helper calls per routine ticket, measured rather than promised; native spawn/wait/Git calls and manual G5 setup/wait are separate.

**Completion:** every attempt has an adequate evidence-backed route or a cause-specific blocker; no same-method repeat proceeds without a distinguishing change.
