# Raw observations — final V1 qualification rerun

Date: 2026-09-13 (Europe/Minsk)

Scope: current snapshot after `WAVE 1 COMPLETE` and `WAVE 2 COMPLETE`.
Fixtures were disposable and created under `/private/tmp` or Python's
disposable temporary directory. No production remediation, E10, or global
installation was performed.

## Runtime and package

- `codex --version`: `codex-cli 0.153.4`.
- Python: `3.14.7`; Git: `2.39.5`.
- Package surface contains `tools/ledger.py` and deterministic helper CLI;
  no orchestrator/compaction/restart runtime is shipped in this workspace.
- `python3 -m unittest discover -s tests -v`: 14/14 PASS.
- `py_compile` for `tools/ledger.py`, `tools/dashboard.py`, and the
  qualification harness: PASS.
- JSON parse for `schemas/contracts.schema.json`: PASS.

## E03-M regression

The two frozen E03-M regression tests passed:

- frozen packet/environment/context/acceptance files validate;
- copied frozen seed repo imports the existing manual acceptance return and
  remains resumable/idempotent, reaching `INTEGRATED` with the lease released.

The manual G5 roundtrip was not repeated, per request.

## E01

Actual disposable run `/private/tmp/codex-autopilot-v1-qualification-20260913/E01`:

- valid gate publication: exit 0;
- stale owner/revision attempt: exit 2, `stale orchestrator is fenced`;
- `ledger.prev.json`: present and schema-valid;
- corrupt current ledger: status returned exit 2 with recovery instruction;
- `recover` from verified snapshot: exit 0, `RECOVERING`, revision 3;
- after 100 further gate publications: 8 unpinned snapshots retained plus a
  pinned recovery snapshot;
- focused Wave 1 effect-journal and cancel tests also passed.

Observed result: PASS for the exercised E01 matrix.

## E04b

Actual disposable Git fixture:

- tracked modification, untracked file, ignored output, and in-root symlink
  were all present in `actual_paths`/`changed_paths`;
- the audit returned `pass:false`, listed all undeclared/out-of-zone paths,
  and preserved symlink fingerprint/type information;
- focused Wave 1 audit test passed ignored-path inclusion and escaping
  symlink rejection;
- focused effect-journal and cancellation/reconciliation tests passed.

One old harness worker-return fixture omitted the now-required
`evidence_ref`; that is a stale TEST FIXTURE defect, not a product finding.
The new local E08 defect below caused the qualification stop before the
remaining E04b destructive-state arms (`clean`/`stash`/hook) could be rerun in
this final pass.

Observed result: partial core PASS; overall E04b qualification stopped.

## E05

Current Wave 2 disposable tests passed:

- `adequacy=REJECTED` / unknown-context route was rejected before attempt
  creation;
- a BLOCKED worker return was durably recorded with a typed cause and was not
  eligible for candidate publication;
- an unchanged repair signature was rejected as no causal progress;
- usage and evidence publication remained attributable.

Comparative model/economic tuning was not treated as a release blocker and
was not run without a supported orchestrator/model runtime.

Observed result: PASS for the implemented functional guard arms; comparative
tuning OUT OF V1 for this package surface.

## E06

Current disposable regression tests passed:

- candidate and separate reviewer attempt authority are distinct;
- empty worker/reviewer evidence is rejected by the closed nested contracts;
- durable conflicting reviewer verdicts require an evidence-backed
  adjudication and a PASS adjudication clears the disagreement blocker.

Frontier/Astra comparison was skipped because it is optional and no such
qualified runtime was available.

Observed result: PASS for required helper-side guard arms; optional frontier
comparison OUT OF V1.

## E07

The frozen E03-M import path regression and cancellation/quiescing guards
passed in the focused suite. The complete fresh micro-project G0–G6 run with
new amendment, repair, pause/resume, cancel run, and actual operator-assisted
G5 was not completed after the E08 stop condition.

Observed result: NOT QUALIFIED — halted by the new E08 implementation defect.

## E08 — new implementation defect

Disposable fixture:

- one READY ticket had lease zone `app.txt` only;
- a valid packet was dispatched and produced a schema-valid `DONE` return;
- the return claimed `files:[{"path":"other.txt","operation":"modify"}]`;
- `ingest-return --kind worker` exited 0 and stored the return;
- resulting attempt state was `RETURNED`, ticket remained `RUNNING`, issue list
  was empty.

Expected: reject/quarantine the return as outside the lease, or create a
typed blocking finding before it can progress. Actual: accepted. This is a
new local implementation defect in the current snapshot, not a stale test
expectation and not an OUT OF V1 case.

The previously fixed E08 arms (dependency cycle, unknown schema, nested
contract completeness, amendment consumer closure, stale/manual binding,
adjudication) are covered by the 14/14 regression suite, but E08 overall is
FAIL and the qualification stopped immediately on this finding.

## E09

An actual disposable six-ticket, three-level DAG was seeded and inspected:

- initial ledger bytes: `6072`;
- `brief` bytes observed: `3318`;
- usage schema/publication surface reported `tokens:null` with
  `token_reason=token_meter_unavailable`;
- counters/trace were observable and initially zero before a real
  orchestrator run;
- no shipped operation can force compaction, restart an orchestrator without
  its old chat/handles, or attribute model/helper turns through that run.

Observed result: BLOCKED/UNKNOWN for the required economy/context/
compaction/restart qualification. Null token handling itself is correct; the
missing runtime is an explicit limitation, not a fabricated metric.
