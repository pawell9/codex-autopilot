# E03-M repeat under targeted manual-G5 policy revision

This repeat uses the same prepared attempt, candidate, intent, packet, bundle,
and pristine export. Nothing is recreated. The previous `BLOCK` is retained as
a contract/policy finding; it is not a candidate or implementation defect.

## Frozen subject

- Run: `e03m-manual-g5-2026-09-13`
- Attempt: `A-E03M-WORKER-1`
- Intent revision: `intent-v1`
- Criterion: `C-E03M-1`
- Candidate fingerprint/commit: `0a5d2b78af78411f7c6b71405e262092b78da1eb`
- Candidate tree: `d687e71ab613ea65a1ec578436a8a2662ab546ec`
- Packet SHA-256: `94623e39528f122a4227bd5db6c60409047fcfa17d8204143c1f1f1e283b683b`
- Projection SHA-256: `79aedaeec289fb3cb43e0b355c63801c8cc1a1b70ce135c1bc13aff0c724ac7e`
- Manifest/export fingerprint: `3698d5ed9dfb344d4c2228da5cdbba2840dabc44eec889fea141cf9a1a70d98a`

## Revised policy boundary

`MANUAL_ATTESTED_CLEAN` means a new independent reviewer session with clean,
attested transferred inputs and context. The reviewer receives only
`g5-bundle/` and `candidate-export/`. Authoritative repo, `.autopilot`, Git
history, implementation history, project memory, credentials, and connectors
are not transferred or used as project inputs. The candidate export is
immutable and all hashes/manifest/packet/export identities remain mandatory.

The environment receipt records only observable review-surface topology,
accessible input paths/tool connections, effective grants, and nonsecret probes.
`authoritative_absent=true` is scoped to the declared transferred review
surface: no authoritative project/state/history input was present or used. It
does not claim proof about unobservable underlying host files, hidden provider
memory, or every system credential-like environment variable. An observed
authoritative project input, connector use, credential use, contaminated
context, tampered export, or missing oracle remains blocking. `STRICT_FRESH` is
never assigned.

## Reviewer prompt

Start a new independent Sol High Temporary Chat in an external review surface.
Use only the two transferred directories `g5-bundle/` and
`candidate-export/`. Do not fork/resume any author or prior reviewer session.
Do not import project memory, chat history, implementation narrative,
authoritative repository/state, Git history, credentials, connectors, or any
other project files. Do not modify the pristine candidate export and do not
repair product files.

Perform the current-intent G5 check independently. Verify the transferred
inventory against `g5-bundle/manifest.json`, verify packet/projection/manifest
hashes, and inspect the pristine candidate export for `C-E03M-1`. Report
independent checks/evidence. A user approval is not a G5 result.

The host/platform may expose properties that are not observable to the
reviewer. Do not claim `STRICT_FRESH` and do not treat an unobservable host
property as a blocking failure. If authoritative project input or connector
access is actually observed or used, return `BLOCK` and record it. If a
required oracle or clean-input fact cannot be established, return
`UNVERIFIABLE` or `BLOCK`.

Return exactly these three JSON files, with no extra top-level keys beyond the
schemas below.

### `acceptance-return.json`

Required top-level keys: `identity`, `candidate_fingerprint`, `verdict`,
`outcomes`, `checks`, `findings`. Use:

```json
{
  "identity": {
    "run_id": "e03m-manual-g5-2026-09-13",
    "attempt_id": "A-E03M-WORKER-1",
    "packet_hash": "94623e39528f122a4227bd5db6c60409047fcfa17d8204143c1f1f1e283b683b",
    "intent_revision": "intent-v1",
    "epoch": 0
  },
  "candidate_fingerprint": "0a5d2b78af78411f7c6b71405e262092b78da1eb",
  "verdict": "PASS",
  "outcomes": [
    {
      "criterion_id": "C-E03M-1",
      "outcome": "fulfilled",
      "evidence_refs": ["<independent-evidence-ref>"]
    }
  ],
  "checks": [
    {
      "check_id": "<check-id>",
      "outcome": "fulfilled",
      "actual": "<observed-result>",
      "evidence_ref": "<independent-evidence-ref>"
    }
  ],
  "findings": []
}
```

`verdict` must be `PASS`, `BLOCK`, or `UNVERIFIABLE`. Include exactly one
outcome for `C-E03M-1`; do not turn a missing fact into `fulfilled`.

### `environment-receipt.json`

Required top-level keys and exact values:

```json
{
  "receipt_id": "<unique-receipt-id>",
  "status": "PASS",
  "topology": {
    "<observable-review-surface-key>": "<truthful-value>"
  },
  "inventory_hashes": [
    {"path": "g5-bundle/manifest.json", "sha256": "3698d5ed9dfb344d4c2228da5cdbba2840dabc44eec889fea141cf9a1a70d98a"},
    {"path": "g5-bundle/operator-checklist.md", "sha256": "318f1587e70f11238396f8745fef6303d237e614c2543ece0de328d4a256217b"},
    {"path": "g5-bundle/packet.json", "sha256": "94623e39528f122a4227bd5db6c60409047fcfa17d8204143c1f1f1e283b683b"},
    {"path": "g5-bundle/projection.json", "sha256": "79aedaeec289fb3cb43e0b355c63801c8cc1a1b70ce135c1bc13aff0c724ac7e"},
    {"path": "candidate-export/.gitignore", "sha256": "fbc3a2b0c13c7ac1589b89b4f037fe9ee5308a00b3fe77ce87d38938fcafbe0d"},
    {"path": "candidate-export/README.md", "sha256": "63d2cc4bc8682d1348b1028e95909b100c24f41416248aae9cb491db9256cba5"},
    {"path": "candidate-export/app.txt", "sha256": "01afd17aa52c239d0c54efade3f284bce3dc2853680b5bba25849b20187bb717"}
  ],
  "effective_grants": {
    "<observable-grant-key>": "<truthful-value>"
  },
  "boundary_probes": [
    {
      "probe": "<nonsecret-declared-input-boundary-probe>",
      "result": "<truthful-result>"
    }
  ],
  "authoritative_absent": true
}
```

`status=PASS` and `authoritative_absent=true` mean the declared transferred
review surface contained no authoritative project inputs and none were used;
they do not assert unobservable host-wide absence. Do not read credential
values. Known authoritative project access, connector use, or credential use
requires `BLOCK` instead.

### `context-receipt.json`

Required top-level keys and exact values:

```json
{
  "receipt_id": "<unique-receipt-id>",
  "status": "PASS",
  "grade": "MANUAL_ATTESTED_CLEAN",
  "packet_hash": "94623e39528f122a4227bd5db6c60409047fcfa17d8204143c1f1f1e283b683b",
  "export_hash": "3698d5ed9dfb344d4c2228da5cdbba2840dabc44eec889fea141cf9a1a70d98a",
  "clean_input": true,
  "contamination_absent": true,
  "session_provenance": {
    "<truthful-session-key>": "<truthful-value>"
  }
}
```

Only `session_provenance` is optional. `MANUAL_ATTESTED_CLEAN` is the human
attested clean-input/context grade; it is not `STRICT_FRESH` and is not user
approval. Stop all reviewer writes before returning the three exact JSON files.

