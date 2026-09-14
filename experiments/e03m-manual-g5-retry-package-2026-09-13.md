# E03-M retry manual G5 package

This is a retry for the same frozen candidate and the same prepared attempt.
Do not recreate the candidate, bundle, export, fixture, or ledger. Do not run a
reviewer in the authoring session.

## Frozen identities and hashes

- Run: `e03m-manual-g5-2026-09-13`
- Attempt: `A-E03M-WORKER-1`
- Intent revision: `intent-v1`
- Active criterion: `C-E03M-1`
- Candidate fingerprint / commit SHA: `0a5d2b78af78411f7c6b71405e262092b78da1eb`
- Candidate tree SHA: `d687e71ab613ea65a1ec578436a8a2662ab546ec`
- `g5-bundle/packet.json` SHA-256: `94623e39528f122a4227bd5db6c60409047fcfa17d8204143c1f1f1e283b683b`
- `g5-bundle/projection.json` SHA-256: `79aedaeec289fb3cb43e0b355c63801c8cc1a1b70ce135c1bc13aff0c724ac7e`
- `g5-bundle/manifest.json` SHA-256: `3698d5ed9dfb344d4c2228da5cdbba2840dabc44eec889fea141cf9a1a70d98a`
- Export fingerprint for the context receipt: use the manifest SHA above.
- Candidate export file hashes:
  - `.gitignore`: `fbc3a2b0c13c7ac1589b89b4f037fe9ee5308a00b3fe77ce87d38938fcafbe0d`
  - `README.md`: `63d2cc4bc8682d1348b1028e95909b100c24f41416248aae9cb491db9256cba5`
  - `app.txt`: `01afd17aa52c239d0c54efade3f284bce3dc2853680b5bba25849b20187bb717`

The prepared attempt currently expects packet hash
`94623e39528f122a4227bd5db6c60409047fcfa17d8204143c1f1f1e283b683b`.
The prior pre-review ledger hash is
`0c59a461195d88ff8020615de668651199dfb578ef420a4bfce7e954a7c18e5c`.

## Exact reviewer prompt

Start a new independent Sol High reviewer session in an external isolated
environment. The environment must have no access to the authoring Mac,
authoritative repository, `.autopilot`, Git metadata/history, credentials,
connectors, or project memory. Transfer only `g5-bundle/` and
`candidate-export/`. Use the pristine candidate export for the check; do not
modify it. Do not use or request any other project input. Do not repair product
files. Return three JSON files with exactly the structures below.

The following is a strict contract. Use the exact top-level keys shown. Do not
add free-form top-level keys. Do not return prose instead of JSON. All values
describing observations, topology, grants, and probes must be truthful to the
actual external environment; if a required fact cannot be established, return
`BLOCK` or `UNVERIFIABLE`, not a fabricated PASS receipt.

### `acceptance-return.json`

The production acceptance-return schema requires these exact top-level keys and
no others:

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

`verdict` may only be `PASS`, `BLOCK`, or `UNVERIFIABLE`. The outcome list must
contain exactly one entry for the only active criterion `C-E03M-1`. A `PASS`
requires that entry to be exactly `fulfilled` and requires no blocking finding.
The `checks` entries must describe independent checks, not user assent. If the
verdict is not PASS, preserve the actual outcome and findings.

Runtime-specific requirements enforced by `import-manual` are: identity
`attempt_id` must match; identity `packet_hash` must equal the frozen packet
hash above; if supplied, identity `run_id` and `intent_revision` must match;
candidate fingerprint must match; verdict must be one of the three allowed
values; and every required criterion must appear in outcomes.

### `environment-receipt.json`

The exact formal schema has these required keys, `status` must be `PASS`,
`authoritative_absent` must be `true`, and no other top-level keys are allowed:

```json
{
  "receipt_id": "<unique-receipt-id>",
  "status": "PASS",
  "topology": {
    "<truthful-topology-key>": "<truthful-value>"
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
    "<truthful-grant-key>": "<truthful-value>"
  },
  "boundary_probes": [
    {
      "probe": "<nonsecret-boundary-probe>",
      "result": "<truthful-result>"
    }
  ],
  "authoritative_absent": true
}
```

`import-manual` additionally requires a nonempty `receipt_id`, nonempty
`inventory_hashes`, and nonempty `boundary_probes`. The formal schema requires
`topology`, an array for `inventory_hashes`, an object for `effective_grants`,
and no extra top-level fields. The environment receipt must truthfully establish
that the authoritative repository/state/history and connected tools are absent
from the reviewer environment; a task-level allowlist over a broad host grant
is not sufficient evidence.

### `context-receipt.json`

The exact formal schema has these required keys and no other top-level keys,
except the optional `session_provenance` object:

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

`import-manual` additionally requires a nonempty `receipt_id`,
`grade=MANUAL_ATTESTED_CLEAN`, and an exact `context_receipt.packet_hash`
matching the prepared attempt. The schema requires both 64-hex hashes, literal
boolean `true` for `clean_input` and `contamination_absent`, and literal
`status=PASS`.

Do not reuse the previous malformed receipts. Return the three new exact JSON
files after stopping all reviewer writes. Do not include the authoritative
integrity receipt; it remains with the orchestrator.

