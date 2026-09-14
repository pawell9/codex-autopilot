# Raw observations — V1 qualification pass

Date: 2026-09-13, Europe/Minsk  
Harness: [v1_qualification_harness.py](../v1_qualification_harness.py)  
Disposable root: `/private/tmp/codex-autopilot-v1-qualification-20260913/`

The harness ran `tools/ledger.py` as a subprocess and used only disposable
control/repository roots. It did not invoke E03-M, E10, global installation,
network services, or the original project checkout as a test target.

## Package snapshot

| File | SHA-256 |
|---|---|
| `tools/ledger.py` | `2a4ba5db68dcad68e9fd5c69532b03d56bac13fa69d30774cc40a5597fe476bd` |
| `schemas/contracts.schema.json` | `87fbc8ea142ab4d02b691b38b49484cca5ea9e457fd2e7b3b06d99a79492f57f` |
| harness | `49236f5c0a27e191363fb5d6d3ce2758eecd07934910491ed6cea388038b93e2` |

`python3 -m py_compile tools/ledger.py experiments/v1_qualification_harness.py`
exited 0.

## E01 observations

- A valid `gate` publication advanced revision `1 → 2`; the next publication
  created a valid `ledger.prev.json`.
- A stale owner token was rejected before publication (`owner token mismatch;
  stale orchestrator is fenced`, process exit 2).
- `render-view` generated `views/status.md` from the current ledger and
  reported its source revision/hash.
- After replacing the current ledger with invalid JSON, `status` rejected it
  and the valid previous checkpoint remained separately valid.
- `recover` against that corrupt current ledger also rejected because it first
  calls `load_state`; no recovery publication or durable recovery next-action
  was produced.
- A 100-publication series completed through revision 102. At the end only
  `ledger.json`, `ledger.prev.json`, the intent document, and the generated
  view existed under the run; no recovery snapshot files were created.
- Final current/previous ledger files were each about 2.1 KiB in this fixture.

## E04b observations

- Disposable Git status after foreign dirt and a symlink was:
  `M foreign.txt`, `?? link.txt`, `?? untracked.txt`.
- `ignored.out` existed and matched `.gitignore`, but default
  `audit-write-set` returned `actual_paths` only for `foreign.txt`, `link.txt`,
  and `untracked.txt`; `ignored.out` was absent.
- The audit returned JSON `pass: false` and listed all observed non-zone paths
  as `undeclared_paths` and `outside_zone`.
- A worker dispatch and matching return ingest both completed on the fixture.
- `ledger.py --help` exposed no prepared-effect reconcile, stash/clean safety,
  cancel protocol, or effect-receipt command; `candidate` only consumes an
  already supplied PASS Git receipt.

## E05 observations

- A route with `adequacy: REJECTED`, `context_grade: UNKNOWN`, and
  `fallback_cause: permission` was accepted by `dispatch`.
- The resulting ticket state was `RUNNING`; the route was merely appended to
  the ledger.
- No helper command exposed cause classification, no-progress comparison,
  repair attempt creation, or escalation adjudication.

## E06 observations

- A real disposable Git candidate was created and recorded with a commit SHA.
- A review return with `verdict: PASS`, empty `coverage`, empty `checks`, empty
  `findings`, and no context references was accepted by `integrate`.
- The ticket moved to `INTEGRATED` and a PASS review record was published.

## E07 observations

- The disposable flow reached `prepare-handoff` and `import-manual` with a
  bundle, manifest, context/environment receipts, integrity receipt, and an
  exact structured acceptance return.
- The worker return used `status: BLOCKED`; `candidate` nevertheless accepted
  the candidate Git receipt and moved the ticket toward review.
- A manual acceptance PASS was importable for the single fixture criterion.
- `gate --control CANCELLED` published terminal cancellation directly from the
  accepted fixture without an observable stop/reuse guard or cancellation
  reconciliation step.

## E08 observations

- A two-ticket dependency cycle was rejected by `validate` with
  `ticket dependency graph contains a cycle`.
- A `worker_return` with empty `checks` and empty `criteria` validated
  successfully because nested contract objects have no required fields in the
  effective closed-schema subset.
- The available handoff path validates the supplied projection but does not
  verify the current state intent document reference/hash before preparing the
  bundle.
- Inbox regular-file/non-symlink and packet-hash checks are present and were
  covered by the E04b/E02 fixture contracts.
- No helper path was exposed for adjudicating reviewer disagreement, generated
  source drift after review, missing approved documents, or stale views as
  typed gates.

## E09 observations

- A disposable six-ticket serial DAG was materialized, with one coupled ticket
  and depth three (the required “6–10 ticket, 2–3 level DAG” shape was
  available as a fixture).
- The initial ledger had no `usage` object.
- `brief` returned phase/control/revision/next action and a ledger hash.
- No production compaction hook, context-load receipt, usage publication,
  helper-call attribution, or orchestrator restart-without-chat protocol was
  exposed by the current package.
- Consequently, routine helper-call count, packet/return duplication,
  compaction re-grounding, human handoff/wait cost, and token usage could not
  be measured from an actual V1 run. Token/usage data was not invented.
