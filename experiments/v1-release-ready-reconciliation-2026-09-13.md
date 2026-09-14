# V1 release-state reconciliation — 2026-09-13

**CODEX-AUTOPILOT V1.0.0 — FROZEN / RELEASE READY.**

**Current verdict: `V1.0.0 FROZEN / RELEASE READY`.**

This reconciliation supersedes the pre-remediation blocked checkpoint in
`v1-final-qualification-2026-09-13.md` and the matching top sections of
`STATUS.md` and `SUMMARY.md`. Those records remain below as historical
provenance; they are not the current verdict.

## Evidence

| Gate | Current result | Evidence |
|---|---|---|
| E01 | PASS | `v1-qualification-rerun-2026-09-13.md`; Wave 1/2 regression coverage |
| E03-M | PASS | `e03m-manual-g5-2026-09-13.md`: manual G5 PASS, lease reconciliation, G6 `ACCEPTED` |
| E04b | PASS | Prior current-surface arms in `v1-qualification-rerun-2026-09-13.md`; `python3 experiments/e04b-target-mismatch-2026-09-13.py` returned `qualified: true` and rejected `effect receipt target mismatch` |
| E05 | PASS (scoped) | `v1-qualification-rerun-2026-09-13.md` and Wave 2 tests |
| E06 | PASS (scoped) | `v1-qualification-rerun-2026-09-13.md` and Wave 2 tests |
| E07 | PASS | `e07-fix-2026-09-13.md`; current regression suite |
| E08 | PASS | Wave 2 outside-lease quarantine test; current regression suite |
| E09 | PASS | Fresh `python3 experiments/e09-release-qualification-2026-09-13.py`: exit 0, `qualified: true`, 6 tickets, DAG depth 3, released worker leases, restart/takeover and usage trace |

## Reproduced checks

- `python3 -m unittest discover -s tests -p 'test_*.py' -v` — **28/28 PASS**.
- `python3 experiments/v1_40_ticket_qualification.py` — **40-TICKET
  QUALIFICATION PASS**; schema round-trip, repair, pause, recovery, and
  terminal acceptance all passed.
- E04b target-mismatch runner — **PASS**; wrong-target receipt rejected and
  operation remained `prepared`.
- E09 runner — **PASS**; token meter is explicitly unavailable on this
  runtime (`tokens: null`, `token_reason: token_meter_unavailable`), which is
  retained as a declared limitation rather than a green token claim.

## Package provenance

Current production implementation hashes at reconciliation:

```text
SKILL.md                       4134f4e3c87de61e4d543cf066ecda31fb988fe4fb37812769dbd79e3d29f0a7
tools/ledger.py                95d83f9632f223859941b40fe918efe7978ccaa891d1cb39c037d84236d6845a
schemas/contracts.schema.json  e6dbfeca22df65334d6a6e15b4bdbdf66504a13171f0d70d56362e0b70fbdc7c
```

E10 remains explicitly post-V1 and is not a release blocker. Strict automatic
critical/G5 transport remains unqualified; V1 uses the tested
`MANUAL_ATTESTED_CLEAN` user-assisted route described by the production
acceptance contract.
