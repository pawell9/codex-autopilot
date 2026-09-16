# Verify, G5, and G6

Read `contracts/reviewer.md` final acceptance, `references/safety.md` manual environment, and `references/ledger.md`. G5 is independent product acceptance against the current authorized intent; G6 is the final record. Never use routine review or user assent as a substitute.

## Prepare G5

Freeze the exact integrated candidate SHA/tree and current intent revision. Build a deterministic allowlist projection containing current goal, exact requirement wording/IDs, approved product amendments and provenance, every active observable criterion, exclusions/deferred items, benign launch/setup facts, allowed test resources, constraints, and the return schema. Exclude spec/plan/tickets, worker returns, test-pass summaries, review history, repair narrative, commit history, credentials, `.git`, and `.autopilot`.

Validate that every active criterion appears once, no hidden self-rating/status field exists, approved amendments only are included, and the candidate/export fingerprints match. Missing live content is an explicit UNVERIFIABLE/oracle blocker, not silent scope reduction.

## Required V1 transport

For every G5 round and every required critical axis, use `acceptance_transport=user_assisted` until a strict automatic transport is separately qualified. Prepare the immutable export, packet, projection, manifest/hash, environment requirements, return schema, and operator checklist automatically. Then wait in `BLOCKED` with `manual_review_pending` while the user:

1. Starts a new independent reviewer session with no fork/resume, project-memory/chat import, author or worker narrative, or authoritative repo/state/implementation inputs passed to the reviewer. Known connector use or known access to authoritative state is ineligible.
2. Transfers only the bundle and records packet/export hashes, session/launch provenance when observable, operator clean-input attestation, environment topology/permission receipt, and nonsecret denied/absent boundary probes.
3. Runs the reviewer on the pristine export, not a mutation copy, and returns exact structured evidence. A critical axis is a separate mandate. The reviewer supplies no product repair.

The setup receipt must identify the observable review-surface topology, accessible input paths/tool connections, transferred input inventory/hashes, effective grants, and operator attestation that no authoritative repository/state/history or implementation narrative was transferred or used. The receipt's absence claim is scoped to the declared review surface and inputs; it is not a proof about unobservable underlying host files, hidden provider memory, or unrelated system environment variables. Known authoritative access, connector use, contaminated context, missing oracle, malformed return, or missing interruption/resume evidence remains BLOCKED. This is `MANUAL_ATTESTED_CLEAN`, not `STRICT_FRESH`; the production package's E03-M qualification is recorded in the release-state reconciliation, but every run must still produce fresh receipts and evidence.

## Import and acceptance

Import through the validated file/message contract only. Run state-bound
`validate-return --kind acceptance`, then require matching attempt/packet/
subject/intent, environment and context receipts, every active criterion/axis
outcome, independent checks/evidence, and a PASS verdict. Before publication,
stop the reviewer and run the authoritative integrity barrier against
candidate, run branch, ledger/docs/evidence baseline. Any mismatch,
stale/tampered export, known authoritative or connector access, contaminated
session, missing oracle, malformed return, or plain sign-off invalidates the
result and keeps the run blocked. Unobservable host-layer properties do not
become a hidden PASS claim and are reported as residual trust in the
receipt/report.

All accepted findings in one G5 round form one dependency-ordered repair wave. Targeted re-reviews close its findings, then one fresh G5 runs on the common new candidate. A contract/intent amendment goes through its affected gates and gets a new projection. `UNVERIFIABLE`, partial, missing, or blocking outcomes cannot become PASS.

## G6

After a valid per-criterion G5 PASS, verify current revisions did not change, all operations/leases/blockers are closed, and any separately requested human acceptance exists. Generate the derived status/final report with exact candidate, intent, transport, setup/context evidence grade, reviewer provenance, limitations, exclusions, risks, and intervention counts. Publish G6 atomically and transition to `ACCEPTED`. Do not push, deploy, message, merge to a default branch, or announce release unless separately requested and authorized.

**Done when:** a fresh independent reviewer has returned PASS for every active criterion on the unchanged current candidate with validated setup/return/integrity receipts, then G6 is durably recorded; otherwise the exact blocker and next action remain visible.
