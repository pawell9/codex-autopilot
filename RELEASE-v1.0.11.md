# Codex Autopilot v1.0.11

Patch release for preserving an audited non-empty `BLOCKED`/`HANDOFF` worker
write-set as a continuation-only candidate.

The new owner-authorized transition requires a current typed external or
out-of-scope blocker, passing required ticket checks apart from checks directly
attributed to that blocker, a non-empty exact base-to-candidate write-set
audit, and current lease and repair-provenance validation. It records the
candidate, audit, return, blocker, and authorization as immutable evidence. The
ticket and lifecycle remain `BLOCKED`; a continuation candidate can receive
independent review or seed a later authorized repair, but cannot be integrated
as `DONE`. In-scope failed checks, audit failures, missing provenance,
out-of-lease paths, or quarantined leases reject the transition.

## Verification

```bash
python3 -m unittest discover -s tests -v
python3 experiments/v104_lifecycle_qualification.py
python3 experiments/v1_40_ticket_qualification.py
```

After installing the runtime package, verify `ledger.SKILL_VERSION ==
"1.0.11"` and SHA-256 parity for every runtime file listed by the install
commands in `README.md`.

## Current WORKER-05 recovery

The mounted Idea Scout run was inspected read-only. At the time of this
release, its ledger was revision 52 with SHA-256
`161bbb6e4e1744b9dc72bd4eb035fe8fb175786ad866af1c1d5026eea9785cfe`. Ticket
`T02-R17` and attempt `T02-R17-WORKER-05` are `BLOCKED`/`RETURNED`; the exact
attempt base is `9aa5501870352b87538355d14bb68dbde544c3ed`. Its active lease
contains only `modify` for `migrations/009_v2_core.sql`,
`tests/test_v2_migrations.py`, and `tests/test_v2_store.py`. Focused tests,
integrity checks, and Ruff pass. `T02-OFFLINE-SUITE` is the sole failed check,
and its 11 failures require evaluation-v2 resources absent from the exact
base and outside the lease. Criterion `C-V2-01` remains unsatisfied for that
reason. No evaluation resource or lease change is part of this recovery.

The checkout is currently clean relative to its base except for these three
tracked paths, with the following observed SHA-256 values:

```text
migrations/009_v2_core.sql  7f3ee998e4bd6c6c0a32e9c5061f8fb55b34f865d2a76bee6248982f440fac91
tests/test_v2_migrations.py f22258040c3199b6d25de18d5b12f4843b84a7242f74a6e29ca80028627e51cf
tests/test_v2_store.py      b8661e859c4a195b404ad2bd72d2f04a71994ddb996b59013c75d55113d9fee1
```

The following Bash sequence verifies those frozen inputs, records owner
authorization for exactly that blocker/check/criterion, prepares the candidate
commit effect, commits only the three existing leased paths, records the Git
receipt, then publishes the continuation at revision 54. It does not edit the
mounted ledger or broaden the worker lease before invoking the new helper.
Stop if any precondition or hash check fails.

```bash
set -euo pipefail

ledger="$(find /Users/pawell_9/Documents -type f \
  -path '*/.autopilot/runs/2026-09-17-idea-scout-v2-successor/ledger.json' \
  -print -quit)"
test -n "$ledger"
run_dir="$(dirname "$ledger")"
control_root="$(jq -r '.repository.control_root' "$ledger")"
runtime="${CODEX_HOME:-$HOME/.codex}/skills/codex-autopilot/tools/ledger.py"
run_id='2026-09-17-idea-scout-v2-successor'
ticket_id='T02-R17'
attempt_id='T02-R17-WORKER-05'
base_sha='9aa5501870352b87538355d14bb68dbde544c3ed'
auth_id='continuation-auth-T02-R17-WORKER-05-01'
operation_id='t02-r17-worker-05-continuation-commit-01'
auth_file='/private/tmp/t02-r17-worker-05-continuation-authorization.json'
commit_receipt='/private/tmp/t02-r17-worker-05-continuation-commit-receipt.json'
checkout="$(jq -r --arg id "$attempt_id" '.attempts[] | select(.id == $id) | .checkout' "$ledger")"
owner="$(jq -r '.owner.token' "$ledger")"
return_ref="$(jq -r --arg id "$attempt_id" '.attempts[] | select(.id == $id) | .return_ref' "$ledger")"

test "$(shasum -a 256 "$ledger" | awk '{print $1}')" = \
  '161bbb6e4e1744b9dc72bd4eb035fe8fb175786ad866af1c1d5026eea9785cfe'
jq -e '
  .revision == 52 and
  .run_id == "2026-09-17-idea-scout-v2-successor" and
  .lifecycle.control == "BLOCKED" and
  (.tickets[] | select(.id == "T02-R17") |
    .state == "BLOCKED" and .current_attempt == "T02-R17-WORKER-05") and
  (.attempts[] | select(.id == "T02-R17-WORKER-05") |
    .state == "RETURNED" and .base_sha == "9aa5501870352b87538355d14bb68dbde544c3ed" and
    .lease.state == "active" and
    [.lease.zone[].path] == ["migrations/009_v2_core.sql", "tests/test_v2_migrations.py", "tests/test_v2_store.py"]) and
  (.issues[] | select(.id == "issue-62c0073109c9529a") |
    .impact == "blocking" and .source_ref == "T02-R17-WORKER-05" and
    .type == "external_test_fixture_blocker" and (.invalidated_by | length) == 0)
' "$ledger" >/dev/null

test "$(git -C "$checkout" rev-parse HEAD)" = "$base_sha"
test "$(git -C "$checkout" status --short --untracked-files=all)" = \
  $' M migrations/009_v2_core.sql\n M tests/test_v2_migrations.py\n M tests/test_v2_store.py'
test "$(shasum -a 256 "$checkout/migrations/009_v2_core.sql" | awk '{print $1}')" = \
  '7f3ee998e4bd6c6c0a32e9c5061f8fb55b34f865d2a76bee6248982f440fac91'
test "$(shasum -a 256 "$checkout/tests/test_v2_migrations.py" | awk '{print $1}')" = \
  'f22258040c3199b6d25de18d5b12f4843b84a7242f74a6e29ca80028627e51cf'
test "$(shasum -a 256 "$checkout/tests/test_v2_store.py" | awk '{print $1}')" = \
  'b8661e859c4a195b404ad2bd72d2f04a71994ddb996b59013c75d55113d9fee1'

cat > "$auth_file" <<JSON
{
  "id": "$auth_id",
  "type": "continuation_candidate_authorization",
  "status": "authorized",
  "decision": "PRESERVE_CONTINUATION",
  "reason": "The complete offline suite failures are caused only by evaluation-v2 resources absent from the exact base and outside the T02-R17 lease; preserve the audited in-lease repair while retaining BLOCKED.",
  "evidence_refs": ["issue-62c0073109c9529a", "$return_ref"],
  "affected_refs": ["T02-R17", "T02-R17-WORKER-05"],
  "blocker_ref": "issue-62c0073109c9529a",
  "blocker_scope": "external",
  "external_check_ids": ["T02-OFFLINE-SUITE"],
  "external_criterion_ids": ["C-V2-01"]
}
JSON

python3 "$runtime" prepare-effect \
  --control-root "$control_root" --run-id "$run_id" --owner-token "$owner" \
  --revision 52 --operation-id "$operation_id" --kind candidate_commit \
  --target "$checkout" --expected-before "$base_sha" --authority-ref "$auth_id"

git -C "$checkout" add -- \
  migrations/009_v2_core.sql \
  tests/test_v2_migrations.py \
  tests/test_v2_store.py
git -C "$checkout" diff --cached --check
git -C "$checkout" commit -m 'T02-R17: preserve blocked continuation candidate'

python3 - "$checkout" "$base_sha" "$auth_id" "$commit_receipt" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

checkout, base_sha, authority_ref, receipt_path = sys.argv[1:]
commit_sha = subprocess.check_output(["git", "-C", checkout, "rev-parse", "HEAD"], text=True).strip()
tree_sha = subprocess.check_output(["git", "-C", checkout, "rev-parse", "HEAD^{tree}"], text=True).strip()
receipt = {
    "status": "PASS",
    "checkout": str(Path(checkout).resolve()),
    "base_sha": base_sha,
    "commit_sha": commit_sha,
    "tree_sha": tree_sha,
    "authority_ref": authority_ref,
}
Path(receipt_path).write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
PY

python3 "$runtime" preserve-blocked-candidate \
  --control-root "$control_root" --run-id "$run_id" --owner-token "$owner" \
  --revision 53 --ticket-id "$ticket_id" --attempt-id "$attempt_id" \
  --authorization-file "$auth_file" --commit-receipt "$commit_receipt" \
  --operation-id "$operation_id"

jq -e '
  .revision == 54 and .lifecycle.control == "BLOCKED" and
  (.tickets[] | select(.id == "T02-R17") | .state == "BLOCKED") and
  (.attempts[] | select(.id == "T02-R17-WORKER-05") |
    .continuation_ref != null and .candidate_sha != null) and
  (.issues[] | select(.id == "issue-62c0073109c9529a") |
    .impact == "blocking" and (.invalidated_by | length) == 0)
' "$ledger" >/dev/null
```

The helper result should report revision 54, `control=BLOCKED`, and
`ticket_state=BLOCKED`. A later review must be prepared against the exact
candidate SHA. Any repair must remain candidate-bound and use the ordinary
owner-authorized repair flow; the external suite resources and lease remain
unmodified.
