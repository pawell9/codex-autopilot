# Qualification summary — current V1 pass and historical spikes

**CODEX-AUTOPILOT V1.0.0 — FROZEN / RELEASE READY.**

The frozen baseline includes the latest real-world remediation fixes, durable
presets, and 40-ticket scale qualification.

## Current V1 release state — 2026-09-13

**Current verdict: `V1.0.0 FROZEN / RELEASE READY`.** See the complete
[release-state reconciliation](v1-release-ready-reconciliation-2026-09-13.md).

The earlier blocked qualification pass remains below as historical provenance
and is no longer current.

| Experiment | Result |
|---|---|
| E01 | PASS (executed arms) |
| E04b | PASS for executed current-surface arms; one negative oracle not independently closed |
| E05 | PASS (scoped functional guards) |
| E06 | PASS (scoped helper guards) |
| E07 | PASS — targeted blocker fixed |
| E08 | PASS |
| E09 | PASS — worker-lease fix, restart/takeover, 6-ticket DAG, usage trace |

E10 remains post-V1. Global installation follows this reconciled release state.

## Historical qualification spike summary

Final verdict: **QUALIFICATION BLOCKED — NOT IMPLEMENTATION READY**.

E02 provides a viable bounded native worker and recoverable return transport.
E04a provides a viable authorized clean Git path. E03 does not provide the
required technical restriction for critical review axes or a strict-clean G5
verifier, so the mandatory pre-implementation qualification gate remains open.
Design files were not changed and implementation did not start.

## Qualification matrix

| Experiment | Overall | Qualified | Failed / unknown |
|---|---|---|---|
| [E02](E02-native-context-and-interruption.md) | PASS with explicit UNKNOWN arms | Packet-only bounded native worker; behavioural clean routine context; parent/child liveness observation; file and handle/message returns; invalid-route no-spawn handling | Child interruption did not stop descendant writer; abrupt process/UI loss UNKNOWN; strict G5 context and actual model/effort UNKNOWN |
| [E03](E03-reviewer-isolation-and-transports.md) | **FAIL / BLOCKED** | Routine coverage/plan/change through native packet-only reviewer, Git export and serialized integrity barrier; persistent tamper detection | Native prevention/write-restore detection FAIL; `codex exec` unavailable because CLI not logged in; custom read-only and native `/review` not exposed; critical/G5 route absent |
| [E04a](E04a-git-approvals-bootstrap-worktrees.md) | PASS | Empty/seed bootstrap, exact staging, local exclude, branch/candidate/repair commits, current-root approval path, denial handling, permitted sibling placement | Outside workspace sibling denied as expected; reusable prefix unused/UNKNOWN; true post-creation Codex session-loss worktree arm UNKNOWN |

## V1 mechanisms justified by evidence

| Concern | Qualified recommendation |
|---|---|
| Worker context / route | Native `spawn_agent` with `fork_turns=none`, exact bounded packet and pointers. Record `BEHAVIOURAL_CLEAN`, not strict freshness. Accept opaque identity only for the tested bounded task class with independent oracle evidence. |
| Routine reviewer transport | Native `fork_turns=none` reviewer on a `.git`/internal-state-free Git export, authoritative target frozen, message return, independent post-stop Git/hash barrier before ingest. Serialize broad-write review against state publication. |
| Critical reviewer / G5 | **No qualified mechanism. Keep blocked.** Do not substitute the routine detection route or a read-only label. |
| Return transport | Prefer attempt-specific temporary-file → atomic `return.json` in an exact child inbox. Recover completed bytes by attempt/version/hash after liveness checks. Native handle/message is fallback and recovery evidence. |
| Interruption / reuse | Preserve child handle and command inventory. Native agent interruption is not writer-stop proof; quarantine until observed completion, qualified process stop, or user attestation covering background writers. |
| Git approval strategy | Native Git boundary, exact repository/root/command/path list, expected HEAD/tree, and recorded prompt/denial counts. No blanket prefix, alternate-tool bypass, global config edit or inferred permission. |
| Checkout mode | Clean exclusive checkout on a unique run branch. A dirty checkout requires user cleanup or a separately qualified sibling root. |
| Worktree mode | Conditional only for matching authorized-parent topology: permanent sibling path outside the primary repo plus shared common-dir permission. Do not enable as default until real session-loss persistence is checked. |

## Blocking conditions

1. Qualify one automatic reviewer transport with strict clean process/session
   input and technical restriction over authoritative filesystem/tool effects.
   The concrete next candidate is authenticated `codex exec --sandbox
   read-only` with ephemeral export, structured output, mutation probes,
   interruption and network/MCP scope observations.
2. If a custom reviewer or native `/review` becomes exposed, test its effective
   default plus live override; configuration labels are not evidence.
3. Active session build and observed child model/effort remain UNKNOWN. Reuse of
   these results requires a matching observable fingerprint or fresh probes.

## Necessary later checks, outside this authorization

- Worktree survival across actual Codex session loss before enabling it as
  recovery authority.
- E01 and E04b only after a separately authorized helper implementation pass.
- E05–E09 before release and E10 post-V1, exactly as design requires.

No implementation action is authorized from this summary. The next permitted
qualification action is a targeted E03 restricted-reviewer rerun after the
authentication/transport condition changes.
