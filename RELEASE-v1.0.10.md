# Codex Autopilot v1.0.10

Patch release that moves required transitive create-to-modify provenance into
`authorize-repair`, before a ticket can enter `READY`.

For a current validated candidate containing paths owned as `create` but not
`modify`, authorization now requires `source_attempt_ref` to name either the
exact current same-ticket worker or the exact candidate-bound finding review.
Missing, stale, forked, or foreign sources fail without a ledger publication.
Ordinary modify repairs remain source-optional, and dispatch still requires an
exact match with the hash-bound authorized contract.

The release also adds one narrow compatibility transition for an authorization
created by an older runtime: when the ticket is already `READY`, the active
authorization is unused, its exact object-bound contract lacks the now-required
source, and current provenance proves the requirement, a fresh
`authorize-repair` may supersede it. The old decision is retained and receives
`invalidated_by`; no attempt, return, closure receipt, snapshot, or revision is
rewritten.

## Verification

```bash
python3 -m unittest discover -s tests -v
python3 experiments/v104_lifecycle_qualification.py
```

After installing the runtime package, verify `ledger.SKILL_VERSION ==
"1.0.10"` and SHA-256 parity for every runtime file listed by the install
commands in `README.md`.

## Exact revision-49 recovery without history rewriting

These values were read from the mounted Idea Scout successor run without
modifying it:

- run: `2026-09-17-idea-scout-v2-successor`
- revision: `49`
- ledger/snapshot SHA-256:
  `8c8e362b3f76211c51c15c7c413f67533392fc20c282c06f0d1b4022345648c3`
- ticket: `T02-R17`, state `READY`
- restored current candidate: `T02-R17-WORKER-03` at
  `9aa5501870352b87538355d14bb68dbde544c3ed`
- unused defective authorization: `repair-auth-T02-R17-05`
- bound contract object:
  `objects/5e6438196579a41607fb447b7e2048c9f6991095098b8c664d5b99e034617bab`
- required source: `T02-R17-WORKER-03`

First verify the frozen input and prepare a replacement contract outside the
run. Do not restore `ledger.prev.json`, copy snapshot 49 over the ledger, edit
JSON in place, delete decision 05, or reuse worker attempt 04.

```bash
ledger='/Users/pawell_9/Documents/Pet-project - поиск идей проектов/.autopilot/runs/2026-09-17-idea-scout-v2-successor/ledger.json'
run_dir="$(dirname "$ledger")"
control_root="$(jq -r '.repository.control_root' "$ledger")"
runtime="${CODEX_HOME:-$HOME/.codex}/skills/codex-autopilot/tools/ledger.py"
run_id='2026-09-17-idea-scout-v2-successor'
owner='owner-20260917-idea-scout-v2-successor-root-01'
replacement='/private/tmp/t02-r17-repair-contract-06.json'

test "$(shasum -a 256 "$ledger" | awk '{print $1}')" = '8c8e362b3f76211c51c15c7c413f67533392fc20c282c06f0d1b4022345648c3'
jq -e '.revision == 49 and .lifecycle.control == "ACTIVE" and
  (.tickets[] | select(.id == "T02-R17") |
    .state == "READY" and .current_attempt == "T02-R17-WORKER-03") and
  (.decisions[] | select(.id == "repair-auth-T02-R17-05") |
    .status == "authorized" and (.invalidated_by | length) == 0)' "$ledger"

jq '. + {source_attempt_ref:"T02-R17-WORKER-03"}' \
  "$run_dir/objects/5e6438196579a41607fb447b7e2048c9f6991095098b8c664d5b99e034617bab" \
  > "$replacement"

PYTHONPATH="$(dirname "$(dirname "$runtime")")" python3 -c \
  'from tools import ledger; assert ledger.SKILL_VERSION == "1.0.10"'
```

Publish exactly one new revision through the helper:

```bash
python3 "$runtime" authorize-repair \
  --control-root "$control_root" \
  --run-id "$run_id" \
  --owner-token "$owner" \
  --revision 49 \
  --ticket-id T02-R17 \
  --finding-ref finding-22bf0f5a4fde-1 \
  --authorization-id repair-auth-T02-R17-06 \
  --repair-contract "$replacement"
```

The result must be revision 50. Verify that the old decision remains, is
invalidated only by decision 06, the new decision is active and unused, and the
ticket remains dispatchable:

```bash
jq -e '.revision == 50 and
  (.decisions[] | select(.id == "repair-auth-T02-R17-05") |
    .invalidated_by == ["repair-auth-T02-R17-06"]) and
  (.decisions[] | select(.id == "repair-auth-T02-R17-06") |
    .status == "authorized" and (.invalidated_by | length) == 0) and
  (.tickets[] | select(.id == "T02-R17") |
    .state == "READY" and .current_attempt == "T02-R17-WORKER-03") and
  (.attempts | all(.repair_authorization_ref != "repair-auth-T02-R17-06"))' "$ledger"
```

At that point the run is recovered. Prepare a fresh worker packet whose repair
object is byte-for-byte JSON-equal to `$replacement`, whose attempt ID is
`T02-R17-WORKER-05`, whose source revision is 50, whose expected base is
`9aa5501870352b87538355d14bb68dbde544c3ed`, and whose allowlist contains only
`modify` for these three paths:

```text
migrations/009_v2_core.sql
tests/test_v2_migrations.py
tests/test_v2_store.py
```

Only when the native worker can be started immediately, dispatch that packet
with revision 50, lease `lease-t02-r17-05`, route
`ROUTE-V3-WORKER-DEEP`, and fresh attempt `T02-R17-WORKER-05`. A successful
dispatch publishes revision 51 and preserves all revision-49 evidence and the
superseded authorization.
