# E02 — native context, freshness, interruption, and returns

Overall verdict: **PASS with explicit UNKNOWN arms** for pre-implementation
worker qualification. A viable bounded native worker route exists. Strict-final
context is not qualified here and is carried to E03. Native interruption is not
writer-stop proof, so recovery must quarantine known/possible descendant tools.

## Provenance and exposed contract

- PATH CLI: `codex-cli 0.153.4`; active session build: **UNKNOWN**.
- Surface: local macOS session, macOS 15.5 (24F74), arm64.
- Effective permissions: workspace-write to the project and temp roots;
  protected Git/config paths require reviewed approval; network restricted.
- Native schema exposes spawn task/message, `fork_turns`, optional agent type,
  optional model and reasoning effort, plus list/wait/interrupt/follow-up.
- Exposed override catalog after rejection: `gpt-6-astra`, `gpt-5.6-sol`,
  `gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-5.5`.
- Actual parent/child model and effort receipts: **UNKNOWN**.

Raw provenance: [initial](raw/provenance-initial.md),
[route](raw/e02-route-results.md).

## Qualification matrix

| Arm | Verdict | Raw observation | Inference / limitation |
|---|---|---|---|
| Positive inherited-context control | PASS | `fork_turns=all` child saw the parent user qualification brief, though not the late synthetic marker | Confirms contamination route; history transfer is selective/timing-bound |
| Minimal-context child | PASS (behavioural) | `fork_turns=none` child read packet marker and reported no substantive parent conversation | Operational clean evidence for bounded worker/routine review; not strict isolation |
| Strict final context | UNKNOWN | No inspectable child input contract or concrete runtime receipt; non-recall only | Must use E03 clean process/session route or remain blocked for G5 |
| Bounded opaque worker adequacy | PASS | Packet read and bounded local writer both completed correctly | Adequate only for representative bounded task; identity remains opaque |
| Parent native interruption → child liveness | PASS | Parent became interrupted; published child remained running and completed | Child can outlive parent; takeover must reconcile child handle/inbox |
| Child native interruption → descendant stop | FAIL | Child marked interrupted, but its running shell later published final return | Agent status is not stop proof; exact writer remains quarantined until completion/strong evidence |
| Abrupt process/session loss | UNKNOWN | No safe isolated runtime process-loss control exposed | Requires a future build/surface harness; user attestation path remains required |
| UI disconnect loss | UNKNOWN | No controllable UI disconnect arm exposed | Do not transfer native-interrupt result to disconnect semantics |
| Completed file return recovery | PASS | Atomic `return.json` survived lost/interrupted parent and was imported by inspection without respawn | Qualified for attempt-specific inbox with stop/version/hash checks |
| Message/handle recovery | PASS | Child completion remained visible by canonical native handle after parent interruption | Handle status is delivery evidence, not writer-stop proof |
| Partial temp | PASS | `return.tmp` existed without final file before rename | Temp is not completion; producer liveness still needs reconciliation |
| Duplicate/stale payload discrimination | PASS (identity observation) | Exact duplicate bytes/hash match; stale fixture has different attempt ID/hash | Actual schema/helper ingest is intentionally not implemented; rejection mechanics remain E08/E01 |
| Invalid model request/no duplicate spawn | PASS | Native request rejected before handle; inventory contained no attempted child | No blind fallback/retry occurred |
| Model/effort inheritance | UNKNOWN except exposed full-history rule | Tool contract states full-history forks inherit; no observed identity/effort receipt | Do not guess actual model; `fork_turns=none` adequacy is empirical, not inherited identity proof |

## Raw observations versus inference

Context observations are recorded in [context results](raw/e02-context-results.md).
Parent/child state and durable return are in
[interruption results](raw/e02-interruption-results.md). The contradictory
single-PID check and later write are preserved in
[cancel results](raw/e02-cancel-results.md); the later write controls the
inference. Return fixture hashes:

```text
completed=17dfce6f01e3d9112db4d1042a9cbd3f3f4273dc2f358f99ff06063ec9309402
duplicate=17dfce6f01e3d9112db4d1042a9cbd3f3f4273dc2f358f99ff06063ec9309402
stale=d0b335d6a1ade0ba26037fd3c4d16fffd0d12d82584fe92b9d5bba169bc5797b
```

## Qualified E02 disposition

- Worker context/route: native `spawn_agent` with `fork_turns=none`, exact
  packet and pointers; record `BEHAVIOURAL_CLEAN` for the tested bounded route,
  never `STRICT_FRESH`. Opaque model is acceptable only with task-class
  adequacy evidence.
- Return: attempt-specific atomic file is preferred when the child may write
  its exact inbox; canonical handle/message is recovery/fallback. Completed
  payload is reusable after independent identity/integrity/liveness checks.
- Interruption/recovery: `interrupt_agent` stops the agent envelope but not
  reliably its in-flight tool. Preserve handle, command inventory, inbox and
  target quarantine; reuse only after observed bounded completion, qualified
  exact process stop, or explicit user attestation covering background writers.
- Strict G5: no native child route qualified by E02. E03 must supply a clean
  process/session transport.

## Blockers and next checks

- A build-identifiable harness is still needed for abrupt process loss and UI
  disconnect semantics.
- Exact descendant process-group control/receipt is not exposed here.
- E03 must qualify ordinary independent review plus critical filesystem
  restriction and strict clean final context.

