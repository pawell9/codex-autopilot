# Codex Autopilot v1.0.5

Release date: 2026-09-16
Type: backward-compatible review-currentness patch
Compatibility floor: schema 1.0 / creation release v1.0.0

v1.0.5 repairs legacy design-review currentness without deleting or
re-adjudicating audit history. It adds the owner/revision-fenced
`migrate-review-currentness` operation and keeps the current publication,
reviews, returns, verdicts, findings, and evidence immutable apart from
explicit `invalidated_by` currentness metadata.

## Qualification

Run from the release checkout:

```bash
python3 -m py_compile tools/ledger.py tools/dashboard.py
python3 -m json.tool schemas/contracts.schema.json >/dev/null
python3 -m json.tool design/lifecycle-model.json >/dev/null
python3 -m unittest discover -s tests -v
python3 experiments/v104_lifecycle_qualification.py
git diff --check
```

The ordinary suite is fully offline. The historical V5 production-checkpoint
audit is opt-in and is not part of v1.0.5 qualification. The required V12
regression uses a sanitized synthetic revision-77 fixture with the specified
publication/review/packet identities and no production owner token.

## Install and verify helper version/hash

Install with the repository's canonical file-copy workflow:

```bash
release_root="/path/to/codex-autopilot"
install_dir="${CODEX_HOME:-$HOME/.codex}/skills/codex-autopilot"
mkdir -p "$install_dir"/{agents,contracts,dashboard,migration-manifests,phases,references,release-assets/v1.0.4,schemas,tools}
cp "$release_root/SKILL.md" "$install_dir/"
cp "$release_root/agents/openai.yaml" "$install_dir/agents/"
cp "$release_root"/contracts/{reviewer,worker}.md "$install_dir/contracts/"
cp "$release_root/dashboard/index.html" "$install_dir/dashboard/"
cp "$release_root"/migration-manifests/*.json "$install_dir/migration-manifests/"
cp "$release_root"/phases/{accept,design,execute,intent,plan,recover,start}.md "$install_dir/phases/"
cp "$release_root"/references/{ledger,routing,safety}.md "$install_dir/references/"
cp "$release_root"/release-assets/v1.0.4/*.json "$install_dir/release-assets/v1.0.4/"
cp "$release_root/schemas/contracts.schema.json" "$install_dir/schemas/"
cp "$release_root"/tools/{dashboard,ledger}.py "$install_dir/tools/"

PYTHONPATH="$install_dir" python3 -c 'from tools import ledger; assert ledger.SKILL_VERSION == "1.0.5"; print(ledger.SKILL_VERSION)'
test "$(shasum -a 256 "$release_root/tools/ledger.py" | awk '{print $1}')" = "ebd99e79af2591cbc34d428ffe1f0d05d3372e373a4c9ae03b415896060053c8"
test "$(shasum -a 256 "$release_root/tools/ledger.py" | awk '{print $1}')" = "$(shasum -a 256 "$install_dir/tools/ledger.py" | awk '{print $1}')"
test "$(shasum -a 256 "$release_root/tools/dashboard.py" | awk '{print $1}')" = "$(shasum -a 256 "$install_dir/tools/dashboard.py" | awk '{print $1}')"
```

Restart Codex after installation so a new session discovers the updated skill.

## Apply the migration

Do not edit the ledger, delete findings, replay reviews, create a run, or
bypass a gate. Obtain the existing run's owner token through its normal secure
operator context, then verify the current state read-only:

```bash
run_id="2026-09-16-idea-scout-v2"
python3 "$install_dir/tools/ledger.py" diagnose --control-root "$PWD" --run-id "$run_id"
python3 "$install_dir/tools/ledger.py" status --control-root "$PWD" --run-id "$run_id"
```

For the audited V12 state, verify revision 77, DESIGN/BLOCKED, publication ID
`idea-scout-v2-design-bundle-v12`, fingerprint
`cbbae2bf9b299676e84e8f64d804a85324e79ae868b6f59995cf652a3c06156d`,
and fresh current PASS attempts `G2-COVERAGE-V12-01` and `G3-PLAN-V12-01`
with released leases and subject revision 71. Then run:

```bash
python3 "$install_dir/tools/ledger.py" migrate-review-currentness \
  --control-root "$PWD" --run-id "$run_id" \
  --owner-token "$owner_token" --revision 77
```

The command refuses to mutate unless both fresh current PASS reviews are
matched to their registered RETURNED attempts. Every issue gets an outcome in
the hash-addressed migration report. Missing, conflicting, ambiguous, or
current-publication lineage remains blocking.

## Verify the result and idempotency

After a successful migration, verify that all 13 issue IDs and findings still
exist, the V12 publication and two PASS reviews are unchanged, and only proven
historical blockers have non-empty `invalidated_by`. `status`, `brief`, and the
dashboard must show no historical finding as a current blocker.

Run the migration a second time using the post-migration revision. Capture the
ledger hash before and after; both the hash and revision must remain equal:

```bash
ledger_file=".autopilot/runs/$run_id/ledger.json"
before_hash="$(shasum -a 256 "$ledger_file" | awk '{print $1}')"
revision="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["revision"])' "$ledger_file")"
python3 "$install_dir/tools/ledger.py" migrate-review-currentness \
  --control-root "$PWD" --run-id "$run_id" \
  --owner-token "$owner_token" --revision "$revision"
after_hash="$(shasum -a 256 "$ledger_file" | awk '{print $1}')"
test "$before_hash" = "$after_hash"
```

## Resume the legacy run

Start a new Codex session after installing v1.0.5 and explicitly resume the
existing run:

```text
Use $codex-autopilot to resume run 2026-09-16-idea-scout-v2 from its current ledger.
```

The orchestrator must re-read the ledger and migration report, confirm the
same owner/epoch and unchanged current V12 PASS bindings, and use the ordinary
G2/G3 `gate` transitions. Any remaining current, missing-lineage, or ambiguous
blocker must stop advancement normally.
