# Codex Autopilot v1.1.0 — Master Hardening Plan

**Date:** 2026-09-18  
**Status:** authoritative synthesis for implementation planning  
**Scope:** Codex Autopilot only  
**Current product run:** Idea Scout V2 successor, revision 58, T02 paused  
**Target release:** `v1.1.0`

## 0. Purpose

This document merges two independent Astra Web audits of Codex Autopilot v1.0.11 into one implementation plan.

It is **not** a replacement for the original audits. The four Astra artifacts remain the evidence base:

1. `astra-autopilot-hardening-review.md`
2. `astra-autopilot-hardening-findings.json`
3. `astra-autopilot-reliability-review-2.md`
4. `astra-autopilot-reliability-findings-2.json`

Use this file as the **master implementation contract / index** for v1.1.0.

### Authority rule

When the two audits differ:

1. Prefer directly reproduced/executed evidence over static speculation.
2. Prefer the stricter finding when the other audit does not explicitly disprove it.
3. Preserve both findings when they cover different failure surfaces.
4. Do not downgrade a P0 merely because the second audit grouped it differently.
5. Do not silently reinterpret historical evidence or current Idea Scout state.

## 1. Combined verdict

Both audits independently conclude:

- **Do not resume ordinary Idea Scout T02 execution/integration on Autopilot v1.0.11.**
- A one-off `affected_refs` patch is insufficient.
- A **systemic hardening release is required before continuing.**
- Recommended release: **`v1.1.0`**, not a full rewrite.
- Existing strong mechanisms should be preserved:
  - owner/revision fencing;
  - immutable evidence discipline;
  - strict write-set audit;
  - quarantine barriers;
  - transitive repair provenance;
  - independent review;
  - continuation candidate protections.

The core problem is compositional:

> Individual helpers and guards are often strong, but adjacent transitions do not share one executable definition of candidate, finding, authorization, lease, review, effect and current state.

A command can create a state that passes the current validator but the next normal command cannot safely consume; other paths can bypass accepted BLOCK/review barriers.

## 2. Master structural model for v1.1.0

### 2.1 Shared transition / admission layer

All mutating lifecycle commands should share canonical predicates for:

- run / phase / control;
- owner / epoch / revision;
- intent / design publication;
- ticket identity;
- current candidate;
- parent candidate / provenance;
- active findings / obligations;
- authorization identity and status;
- route / risk / criteria;
- write scope / deny rules;
- lease / liveness;
- effect state;
- required review mandates.

Conceptually:

`verified current state + typed event -> validate -> derive next state -> validate cross-state invariants -> derive projections/next_action -> publish`

Do not implement this as documentation only. The same predicates must be called by actual CLI transitions and by qualification tests.

### 2.2 Explicit current candidate

Separate:

- `current_worker_attempt`
- `last_worker_attempt`
- `current_candidate`

A candidate must be a first-class durable identity with at least:

- candidate ID / SHA / tree / base;
- producer attempt;
- explicit parent candidate;
- quality: `DONE` vs `CONTINUATION`;
- blocker obligations;
- review/integration status.

`current_attempt` must no longer be the only address for candidate state.

### 2.3 One finding / obligation projection

Keep raw review findings immutable.

Add explicit, auditable facts for:

- subject binding;
- current applicability;
- supersession;
- semantic resolution;
- carry-forward verification obligations;
- mirrored issue status.

Historical finding != resolved finding.

All of these must derive one current projection used consistently by:

- status;
- authorize-repair;
- review;
- integration;
- G4/G5/G6;
- `next_action`.

### 2.4 One repair plan contract

Introduce one canonical `RepairPlan` / admission object used by both authorization and dispatch.

It must support:

- bounded `finding_refs[]`;
- exact ticket/review/candidate/intent binding;
- one canonical source candidate;
- per-finding hypothesis;
- per-finding expected proof;
- causal novelty;
- exact write allowlist and deny rules;
- route/risk/criteria;
- exact base / provenance;
- stop conditions.

A repair accepted as READY must be dispatchable unless a **new recorded external event** makes it stale.

### 2.5 Total attempt finalization

Define behavior for the full matrix:

- DONE
- BLOCKED
- HANDOFF
- FAILED
- LOST
- INTERRUPTED
- quarantined

combined with:

- no file changes;
- owned audited changes;
- uncertain / foreign changes;
- prior candidate = none / DONE / CONTINUATION;
- writer stopped / unknown.

Each accepted terminal attempt state must have one of:

- ordinary candidate;
- continuation candidate;
- restore previous candidate;
- safe retry from baseline;
- released reservation;
- quarantine with exact resolution proof requirement.

No narrow incident-specific command should create another dead end.

### 2.6 Unified effect completion

Support:

- `prepared`
- `observed/applied`
- `uncertain`
- `abandoned`
- `finalized`

A real Git commit that already occurred must be adoptable without repeating it.

`candidate` and `preserve-blocked-candidate` should share one strong proof/finalization layer, with different eligibility rules but the same evidence integrity.

### 2.7 Immutable review + aggregate qualification

There must be exactly one authoritative return for a review attempt.

`integrate` must consume an accepted immutable review/qualification reference — never reread alternative bytes as a second ingest path.

Integration should require an aggregate policy over all required reviews / axes for the current candidate.

## 3. Combined P0 scope — must close before resuming Idea Scout T02

The union of both audits yields **nine P0 structural areas**.

### P0-1 — Findings / currentness / grouped repair
Sources: `AH-01`, `REL-01`

Must deliver:

- canonical ticket/candidate binding at review ingest;
- prevention of unaddressable findings;
- append-only recovery for already-ingested findings;
- active/current/history/obligation projection;
- grouped `finding_refs[]` repair authorization;
- per-finding verification and resolution;
- no automatic historical = resolved behavior.

Current R58 requirement:
- bind exactly the three Review05 findings to T02 / current candidate;
- retain seven prior T02 findings as history;
- carry unresolved historical concerns forward unless there is proof of closure.

### P0-2 — Repair admission and provenance consistency
Sources: `AH-02`, `REL-02`

Must deliver:

- one shared repair preflight for authorize + dispatch;
- canonical source candidate normalization;
- stale / foreign source rejection before READY;
- deny precedence everywhere;
- safe revoke/replace for any unused authorization;
- exact idempotent authorization lifecycle;
- continuation no-change repair must restore continuation, not require prior DONE.

### P0-3 — Candidate / attempt lifecycle completeness
Sources: `AH-03`, `REL-02`, `REL-06`

Must deliver:

- explicit current candidate;
- general attempt finalization matrix;
- no-change BLOCK/HANDOFF/FAILED coverage;
- safe partial / lost / interrupted reconciliation;
- candidate survives new failed/no-change attempts;
- recovery replay remains valid after later legal progress.

### P0-4 — Immutable review and integration barrier
Sources: `AH-04`, `REL-03`, `REL-04`

Must deliver:

- one immutable review-ingest path;
- integration consumes accepted immutable review refs only;
- conflicting PASS cannot overwrite accepted BLOCK;
- PASS cannot contain failed required check;
- multiple required reviews are aggregated;
- critical ticket cannot integrate without required critical/manual qualification;
- unresolved blockers / obligations prevent integration.

### P0-5 — Effect / candidate finalization and retry safety
Sources: `AH-05`, `REL-05`

Must deliver:

- uncertain effect can be resolved;
- applied-but-not-linked effect can be finalized without repeat commit;
- abandoned effect is not reported as ready;
- exact replay is idempotent;
- candidate proof is as strong as continuation proof;
- crash boundaries around Git / receipt / ledger are recoverable.

### P0-6 — Central transition guards and derived next_action
Sources: `AH-06`, `REL-06`

Must deliver:

- centralized phase/control/terminal/owner/event admissibility;
- no dispatch in QUIESCING/PAUSED/terminal states;
- terminal predecessor cannot be revived with normal recover;
- reason-aware bounded repair while BLOCKED is explicit;
- `next_action` derived from current verified state;
- never await a terminal/returned producer.

### P0-7 — Immutable storage / publication safety
Source primarily: first audit `AH-07`; supported partially by second audit `REL-11`

This must **not be dropped**.

Must deliver:

- owner/revision/CAS validation before canonical mutation;
- rejected command cannot change canonical referenced bytes;
- existing immutable path can only match identical bytes;
- content-addressed reads re-verify file hash;
- transactional write plan prevents pre-fence mutation;
- exact recovery for publication/snapshot split failures.

Critical reproduced case to preserve as regression:
- stale-owner rejected `amend` must not overwrite canonical document.

### P0-8 — Legacy contract-binding compatibility / migration
Sources: `AH-08`, `REL-10`

R58 contains **13 self-input intersections across 9 tickets**.

Must deliver:

- distinguish accepted specification from produced deliverable / implementation availability;
- common binding validator for new and existing runs;
- read-only legacy diagnostics;
- owner-authorized append-only migration / normalization;
- no silent ref deletion or proposed→active conversion;
- material semantic change => versioned replan / affected G2/G3.

Before live R58 mutation, canonical design documents must be consulted to determine whether each binding is metadata-only misclassification or a real scope/design issue.

### P0-9 — Manual critical / G5 lifecycle
Source primarily: first audit `AH-09`; second audit folds part into `REL-04`

This must **not be dropped**.

Must deliver:

- distinguish ticket review / critical axis / final G5 purpose;
- manual BLOCK materializes durable repairable findings;
- manual PASS with failed checks rejected;
- INTERRUPTED manual review cannot become authoritative silently;
- packet purpose/type consistency;
- critical PASS closes only critical obligation, not final run acceptance;
- G5 BLOCK creates a repair wave with fresh final G5 afterward;
- manual transport uses the same finding / review / integration lifecycle as ordinary review.

## 4. Combined P1 scope — close before T03 / preferably in same v1.1.0 release

### P1-1 — Successor / predecessor / wave lifecycle
Sources: `AH-10`, `REL-07`

Need:

- typed successor manifest;
- predecessor terminal hash / candidate / accepted carry-forward evidence;
- no inherited live leases / authorizations;
- wave close as aggregate predicate;
- no terminal predecessor resurrection;
- repository-level owner/namespace guard.

### P1-2 — Liveness / lease / native runtime observations
Sources: `AH-11`, `REL-08`, `REL-14`

Need:

- distinguish checkout reservation from producer liveness;
- optional runtime start/stop/return observed receipts;
- unknown remains unknown;
- timeout is not proof of stop;
- safe reuse only after exact stop/reconciliation;
- no duplicate spawn on replay.

Runtime limitations must be stated honestly: skill cannot guarantee the host will continue a turn or physically kill all child processes without runtime support.

### P1-3 — Execution binding / packet identity
Source: `REL-09`

Need:

- exact run/ticket/attempt/kind/epoch/intent/design/base binding;
- deny precedence for every path;
- authoritative required criteria/input-contract coverage;
- wrong-ticket return rejection;
- repair scope reduction only via explicit plan.

### P1-4 — Evidence / candidate proof parity
Sources: `REL-11`, first-audit `AH-07`

Need:

- VerifiedObjectStore;
- candidate receipts bound to identity/base/tree/target/authority/audit;
- ordinary DONE candidate cannot be weaker than continuation candidate;
- missing historical receipt cannot be guessed.

### P1-5 — Full reproducible qualification package
Sources: `AH-12`, `REL-12`

Need:

- complete source/test/fixture package;
- all missing qualification dependencies included or replaced;
- real disposable Git;
- deterministic fake runtime;
- public lifecycle commands, not hand-seeded states except explicit legacy/malformed migration fixtures;
- fault injection around all durable boundaries;
- install/source parity;
- separate native-runtime qualification.

## 5. P2 scope

### P2-1 — Refactor ledger.py after correctness
Source: `REL-13`

After P0/P1:

- split pure validators/reducers;
- verified storage;
- domain records;
- transition layer;
- proof validators;
- projections.

Do not start with a wholesale rewrite.

### P2-2 — Runtime metrics / presentation
Sources: `AH-13`, `REL-14`

Separate:

- attempt registrations;
- observed spawns;
- observed stops;
- unknown liveness.

Status/dashboard should display:

- current candidate kind;
- active findings / obligations;
- historical findings count;
- exact executable next action;
- source/grade of runtime observations.

## 6. Qualification suite — use the union, with Q01–Q42 as the canonical matrix

The second audit expands the target suite from Q01–Q40 to **Q01–Q42**.

Use the 42-case matrix as the master qualification target.

Important:

- Q01–Q42 are currently **PROPOSED**, not already passing.
- Diagnostic probes from both audits are regression seeds, not qualification PASS.
- Existing graph/model tests do not prove implementation closure.

Also carry forward first-audit specific regressions not to lose:

- stale-owner rejected amend must not mutate canonical document;
- manual BLOCK creates findings;
- manual PASS with failed check rejects;
- INTERRUPTED manual review cannot import as authoritative;
- manual packet-purpose mismatch rejects before state publication.

## 7. Recommended implementation order

Use one v1.1.0 branch / workstream, but implement in dependency order.

### Phase A — Baseline and safety fences

1. Save current source / test / release baseline.
2. Add failing regression fixtures from both audits.
3. Fix immutable storage / pre-fence publication (`P0-7`).
4. Add semantic schema / writer compatibility floor.
5. Add read-only legacy diagnostics.

### Phase B — Canonical state projections

6. Introduce explicit current candidate.
7. Introduce finding / obligation projection.
8. Introduce typed derived next_action / allowed events.
9. Add shared phase/control/terminal transition table.

### Phase C — Repair and attempt lifecycle

10. Introduce canonical RepairPlan / AttemptPlan.
11. Grouped `finding_refs[]`.
12. Shared authorize/dispatch preflight.
13. General attempt finalization matrix.
14. Continuation / no-change / lost / interrupted / quarantine paths.
15. Source/provenance normalization.

### Phase D — Effects and candidates

16. Typed effect state machine.
17. Applied-effect adoption/finalization.
18. Shared VerifiedCandidateProof.
19. Strong ordinary candidate publication.

### Phase E — Reviews and integration

20. One immutable review acceptance path.
21. Review qualification aggregate.
22. Critical/manual review purpose separation.
23. Manual BLOCK/repair lifecycle.
24. Integration consumes qualification refs only.
25. G5 repair wave / fresh final G5.

### Phase F — Legacy R58 compatibility

26. Dry-run contract-binding compatibility assessment.
27. Implement append-only binding normalization / migration.
28. Implement Review05 finding-binding recovery.
29. Build current/history/carry-forward projection.
30. Rehearse R58 recovery on copy only.

### Phase G — P1 runtime / ownership / successor

31. Successor/predecessor manifest / repo ownership.
32. Liveness vs reservation.
33. Execution identity/scope.
34. Runtime observation receipts where possible.

### Phase H — Qualification

35. Implement Q01–Q42.
36. Add durable boundary fault injection.
37. Add same-byte and conflicting replay tests.
38. Complete release package / fixtures / parity checks.
39. Native runtime conformance tests.
40. Independent diff/reliability review before release.

## 8. Definition of Done for v1.1.0

Do not release / resume Idea Scout merely because unit tests are green.

Required:

1. All P0 closed.
2. All P1 closed for general v1.1.0 release.
3. Q01–Q42 implemented and passing.
4. All reproduced negative probes from both Astra audits now fail safely or recover correctly.
5. Old positive duplicate/idempotence controls remain no-op.
6. Fault injection around every durable boundary has a safe result.
7. Complete source/test/fixture package reproduces CI.
8. Source/runtime parity verified.
9. Legacy R58 read-only migration rehearsal passes.
10. No original raw return / frozen publication / predecessor history is rewritten.
11. All ambiguous legacy semantics remain blocked until owner decision/evidence.
12. Native runtime limits are explicitly documented and tested where possible.
13. Final independent review of v1.1.0 diff/state machine is PASS.

## 9. Idea Scout revision 58 — do not recover until v1.1.0 is qualified

Current frozen anchors:

- run: `2026-09-17-idea-scout-v2-successor`
- revision: `58`
- phase/control: `EXECUTE / BLOCKED`
- ticket: `T02-R17`
- current worker: `T02-R17-WORKER-05`
- continuation candidate: `ef8da4ff49cc7f8014d90f463acf8319ad7c1335`
- current review: `T02-R17-REVIEW-CODE-05`
- current review verdict: `BLOCK`
- current Review05 findings: 3
- previous T02 code findings: 7
- additional historical design findings: 11
- external blocker: `issue-62c0073109c9529a`
- stored next_action is stale

Do not:

- edit ledger manually;
- rewrite original Review05 bytes;
- re-ingest a modified Review05;
- mark historical findings resolved only because newest review omitted them;
- integrate Worker05 continuation;
- reset candidate to Worker03 and discard Worker05;
- weaken / deselect failing suite solely to get DONE;
- silently delete the 13 self-input contract refs;
- revive predecessor;
- treat active lease as proof of running process;
- treat PASS text as proof of actual successful checks.

## 10. Target R58 recovery after v1.1.0

Only after v1.1.0 qualification:

1. Re-verify live revision / owner / epoch / intent / candidate / Git state.
2. Verify source/runtime v1.1.0 compatibility.
3. Run read-only semantic migration classification.
4. Resolve the 13 legacy input/output intersections:
   - metadata-only normalization only when semantic equivalence is proven;
   - otherwise versioned replan / affected G2/G3 / successor as required.
5. Append exact Review05 binding-reconciliation events for the three current findings.
6. Build current/history/carry-forward obligation projection.
7. Keep unresolved external fixture blocker.
8. Create one grouped repair authorization for the three current implementation findings.
9. Use Worker05 continuation candidate as exact repair parent/base identity.
10. Transfer reservation only after stop / clean-candidate proof.
11. Dispatch one bounded repair.
12. If result still BLOCKED:
    - nonempty valid changes -> continuation;
    - no-change -> restore current continuation safely;
    - own/in-scope failure -> do not preserve as external.
13. Resolve evaluation resources/oracle separately through proper authority.
14. Produce ordinary DONE candidate only when required criteria/checks genuinely pass.
15. Run fresh independent routine review.
16. Run separate required critical migration/data-integrity qualification.
17. Resolve current and carried obligations with explicit proof.
18. Integrate T02 from immutable accepted qualification refs only.
19. Close leases/effects.
20. Only then evaluate T03 readiness.

Do not preassign revision numbers for recovery; durable event count depends on migration and evidence.

## 11. Inputs for the implementation agent

The implementation session must read all five files:

1. `docs/audits/2026-09-18-astra-autopilot-hardening-review.md`
2. `docs/audits/2026-09-18-astra-autopilot-hardening-findings.json`
3. `docs/audits/2026-09-18-astra-autopilot-reliability-review-2.md`
4. `docs/audits/2026-09-18-astra-autopilot-reliability-findings-2.json`
5. `docs/audits/2026-09-18-autopilot-v1.1-master-hardening-plan.md`

This master file is the implementation synthesis.

The original Astra artifacts remain authoritative evidence and should be consulted when implementing or reviewing any specific P0/P1 item.

## 12. Implementation behavior

Do **not** implement each audit finding as an independent hotfix.

Before code changes:

1. reconstruct current v1.0.11 transition model from source;
2. propose the v1.1 semantic state contract;
3. map every combined P0/P1 to that contract;
4. map Q01–Q42 to expected transitions;
5. identify backward-compatibility / migration boundaries;
6. get internal design consistency before implementation.

Then implement in the phases above.

If the implementation agent discovers a conflict between this synthesis and direct evidence in either Astra audit:

- stop that subpart;
- cite the exact source evidence;
- preserve the stricter safe behavior;
- do not silently reinterpret the audit.

## 13. Release philosophy

The objective is not “no bugs ever”.

The objective is:

> A long multi-ticket run should primarily surface project / product / oracle defects, not deterministic orchestration dead ends caused by adjacent Autopilot transitions disagreeing about the same state.

v1.1.0 should be accepted by executable lifecycle closure and recovery evidence, not by the number of local unit tests or by one successful continuation of Idea Scout.
