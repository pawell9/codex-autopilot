# Codex Autopilot v1.0.4

Release date: 2026-09-16
Type: backward-compatible verified patch
Compatibility floor: schema 1.0 / creation release v1.0.0

v1.0.4 closes the requirements/criteria publication dead end and the related
lifecycle gaps found by a full state-machine audit. It preserves legacy
creation provenance and every immutable document, object, review, finding,
evidence record, and publication-history entry.

## Release contents

- Explicit atomic `adopt-requirements` / `publish-requirements` migration.
- Separate packet registration, subject, attempt-created, return-source, and
  ingest-current revisions.
- Read-only state-bound `validate-return` using the same semantics as ingest.
- Atomic reviewer lease closure; explicit LOST/INTERRUPTED termination.
- Current-subject/kind/mandate disagreement detection.
- Transitive supersession fencing with immutable historical evidence.
- Explicit ticket readiness and cause-bound repair authorization.
- Tightened G2–G6 and terminal evidence guards.
- Zero-effect exact retry paths and conflict rejection at representative
  object/document/ledger/Git-effect boundaries.
- Runtime helper/migration provenance and read-only unknown-schema diagnosis.
- Corrected dashboard currentness projection.
- Machine-readable lifecycle model, reachability/mutation tests, realistic
  terminal-ACCEPTED fixture, and exact Idea Scout V5 disposable dry run.

The complete audit, gap severities, transition table, publication/binding
inventory, identity model, and crash matrix are in
`reports/v1.0.4-lifecycle-audit.md`.

## Verification

Run from the release checkout:

```bash
python3 -m py_compile tools/ledger.py tools/dashboard.py \
  experiments/v104_lifecycle_qualification.py \
  experiments/idea_scout_v5_resume_dry_run.py
python3 -m json.tool schemas/contracts.schema.json >/dev/null
python3 -m json.tool design/lifecycle-model.json >/dev/null
python3 -m unittest discover -s tests -v
python3 experiments/v104_lifecycle_qualification.py
python3 experiments/idea_scout_v5_resume_dry_run.py
git diff --check
```

Expected release result: 58 tests PASS; the realistic fixture ends at
revision 48, `ACCEPT/ACCEPTED`; the Idea Scout copy publishes V5 at revision 31 and ends
at revision 33 after fresh G2/G3 registration, with requirements
publication hash
`a400d95c895023e429d48c447a0630fa6214e728eaf008946217ac0a1e17b692`
and V5 canonical publication fingerprint
`6171a6f5b52e5549896c9168ddd54d1e169c6683d9fc648d500935c7f47fd8a4`.
The audited source remains ledger hash
`b67dfaebe64bbf80bf76d535bff2cf4b4eed12ee7030821f7bb6c59dddc8e0c9`
and raw V5 hash
`c0d235e71d7bed87b9da2141767ad17ad66fe9cd1070ff115ecb989cee3c1f33`.

## Migration behavior

Existing schema-1.0 ledgers from v1.0.0 through v1.0.3 remain readable. Their
`skill_version` is not rewritten. The first v1.0.4 mutation adds verifiable
runtime provenance. Requirements adoption is permitted only before execution,
with no active/quarantined lease or unresolved effect, and only for an exact
current-intent/epoch manifest. Same bytes after a lost response return the
already-published revision without another mutation. Unknown schemas remain
read-only.

## IDEA SCOUT RESUME

The commands below intentionally stop before any Idea Scout product
implementation. They do not edit its ledger or V5 manually and do not reuse
old G2/G3 verdicts.

1. Install this verified release from the release checkout and confirm the
   effective helper version:

```bash
release_root="/Users/pawell_9/Documents/codex-autopilot"
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
PYTHONPATH="$install_dir" python3 -c 'from tools import ledger; assert ledger.SKILL_VERSION == "1.0.4"; print(ledger.SKILL_VERSION)'
```

2. Enter the Idea Scout control root and define the exact audited inputs:

```bash
cd "/Users/pawell_9/Documents/Pet-project - поиск идей проектов"
run_id="2026-09-16-idea-scout-v2"
owner_token="owner-20260916-idea-scout-v2-root-01"
ledger_file=".autopilot/runs/$run_id/ledger.json"
v5_file=".autopilot/runs/$run_id/sources/design-bundle-v5-proposed.json"
manifest_file="$install_dir/migration-manifests/idea-scout-v2-requirements-v2.json"
```

3. Perform read-only schema/state validation at revision 29 and verify the
   exact authoritative ledger hash:

```bash
python3 "$install_dir/tools/ledger.py" diagnose --control-root "$PWD" --run-id "$run_id"
python3 "$install_dir/tools/ledger.py" validate --file "$ledger_file" --kind ledger
test "$(shasum -a 256 "$ledger_file" | awk '{print $1}')" = "b67dfaebe64bbf80bf76d535bff2cf4b4eed12ee7030821f7bb6c59dddc8e0c9"
```

4. Verify revision 29, DESIGN/BLOCKED, owner epoch 0/token, no active or
   quarantined lease, and the V4 current fingerprint:

```bash
python3 -c 'import json; p=".autopilot/runs/2026-09-16-idea-scout-v2/ledger.json"; s=json.load(open(p)); assert s["revision"]==29; assert (s["lifecycle"]["phase"],s["lifecycle"]["control"])==("DESIGN","BLOCKED"); assert s["owner"]["epoch"]==0 and s["owner"]["token"]=="owner-20260916-idea-scout-v2-root-01"; assert s["design_publication"]["id"]=="idea-scout-v2-design-bundle-v4" and s["design_publication"]["publication_hash"]=="9c5364db7683b8a1650f48aec888d504f3f5b2c025ca5a547efa0af1b417c5d2"; assert not [a["id"] for a in s.get("attempts",[]) if a.get("lease",{}).get("state") in ("active","quarantined")]; print("revision 29 / owner epoch 0 / leases clear")'
```

5. Verify the exact prepared V5, plan, criterion-ownership, migration manifest,
   and fresh packet bytes:

```bash
test "$(shasum -a 256 "$v5_file" | awk '{print $1}')" = "c0d235e71d7bed87b9da2141767ad17ad66fe9cd1070ff115ecb989cee3c1f33"
test "$(shasum -a 256 .autopilot/runs/$run_id/sources/plan-v5-source.md | awk '{print $1}')" = "3bd04e4b4aeaa1e010bec0c00d41fd21546a2d22b1d688a6ce63b37e5f4a78e1"
test "$(shasum -a 256 .autopilot/runs/$run_id/sources/criterion-ownership-v5.json | awk '{print $1}')" = "3943fab5dadb40b59b4e89a2a206bff8b2250e9a6dd64d05472a39fdb340d4dd"
test "$(shasum -a 256 "$manifest_file" | awk '{print $1}')" = "a400d95c895023e429d48c447a0630fa6214e728eaf008946217ac0a1e17b692"
test "$(shasum -a 256 "$install_dir/release-assets/v1.0.4/idea-scout-v5-g2-packet.json" | awk '{print $1}')" = "144c0e0ced423ff025c6ee5146eaa3cc060dda7726d3b3b8094f40c5112b00b2"
test "$(shasum -a 256 "$install_dir/release-assets/v1.0.4/idea-scout-v5-g3-packet.json" | awk '{print $1}')" = "1d6052dcea611ab49f154c0d4d97c9a14725d4cc09656a6bdf1c503f9ebab496"
```

6. Atomically adopt the 21 explicit requirements and 21 criteria. Expected:
   revision 30 and publication hash equal to the manifest SHA-256:

```bash
python3 "$install_dir/tools/ledger.py" adopt-requirements \
  --control-root "$PWD" --run-id "$run_id" \
  --owner-token "$owner_token" --revision 29 \
  --manifest "$manifest_file"
```

Expected output includes:

```json
{"publication_hash":"a400d95c895023e429d48c447a0630fa6214e728eaf008946217ac0a1e17b692","requirement_count":21,"criterion_count":21,"revision":30}
```

An exact retry with `--revision 29` is permitted and must return
`"idempotent": true, "revision": 30` without changing the ledger.

7. Publish the exact, unchanged V5. Expected: revision 31 and canonical bundle
   fingerprint `6171a6…fd8a4`; the raw file hash remains `c0d235…1f33`:

```bash
python3 "$install_dir/tools/ledger.py" publish-design-bundle \
  --control-root "$PWD" --run-id "$run_id" \
  --owner-token "$owner_token" --revision 30 \
  --bundle "$v5_file"
test "$(shasum -a 256 "$v5_file" | awk '{print $1}')" = "c0d235e71d7bed87b9da2141767ad17ad66fe9cd1070ff115ecb989cee3c1f33"
```

Expected output includes:

```json
{"bundle_id":"idea-scout-v2-design-bundle-v5","publication_hash":"6171a6f5b52e5549896c9168ddd54d1e169c6683d9fc648d500935c7f47fd8a4","revision":31}
```

8. Verify V5 currentness, V2–V4 supersession, requirements/criteria bindings,
   preserved history counts, and v1.0.4 migration provenance:

```bash
python3 -c 'import json; p=".autopilot/runs/2026-09-16-idea-scout-v2/ledger.json"; s=json.load(open(p)); assert s["revision"]==31; assert s["design_publication"]["id"]=="idea-scout-v2-design-bundle-v5"; assert s["design_publication"]["publication_hash"]=="6171a6f5b52e5549896c9168ddd54d1e169c6683d9fc648d500935c7f47fd8a4"; h={x["id"]:x["status"] for x in s["design_publication_history"]}; assert h["idea-scout-v2-design-bundle-v2"]==h["idea-scout-v2-design-bundle-v3"]==h["idea-scout-v2-design-bundle-v4"]=="SUPERSEDED" and h["idea-scout-v2-design-bundle-v5"]=="PUBLISHED"; assert len(s["design_publication"]["requirement_refs"])==21 and len(s["design_publication"]["criterion_refs"])==21; assert (len(s["attempts"]),len(s["reviews"]),len(s["findings"]),len(s["issues"]),len(s["evidence"]))==(6,6,19,26,6); assert s["skill_version"]=="1.0.0" and s["runtime_provenance"]["last_mutating_skill_version"]=="1.0.4"; print("V5 current; V2-V4 and all historical evidence preserved")'
```

9. Register fresh G2 and G3 attempts on the V5 fingerprint. These packet bytes
   are bound to publication revision 31; G2 registration produces revision 32
   and G3 registration produces revision 33:

```bash
python3 "$install_dir/tools/ledger.py" prepare-design-review \
  --control-root "$PWD" --run-id "$run_id" \
  --owner-token "$owner_token" --revision 31 \
  --review-attempt-id G2-COVERAGE-V5-01 \
  --lease-id LEASE-G2-COVERAGE-V5-01 \
  --packet "$install_dir/release-assets/v1.0.4/idea-scout-v5-g2-packet.json" \
  --review-kind coverage \
  --reviewer-identity independent-g2-reviewer-v5-01 \
  --reviewer-role coverage-reviewer

python3 "$install_dir/tools/ledger.py" prepare-design-review \
  --control-root "$PWD" --run-id "$run_id" \
  --owner-token "$owner_token" --revision 32 \
  --review-attempt-id G3-PLAN-V5-01 \
  --lease-id LEASE-G3-PLAN-V5-01 \
  --packet "$install_dir/release-assets/v1.0.4/idea-scout-v5-g3-packet.json" \
  --review-kind plan \
  --reviewer-identity independent-g3-reviewer-v5-01 \
  --reviewer-role plan-reviewer
```

Expected packet hashes are respectively
`144c0e0ced423ff025c6ee5146eaa3cc060dda7726d3b3b8094f40c5112b00b2`
and `1d6052dcea611ab49f154c0d4d97c9a14725d4cc09656a6bdf1c503f9ebab496`.
Do not reuse G2/G3 attempts or verdicts from V2–V4.

10. Each reviewer must preserve its packet identity, include checks for its
    exact axis and all 21 criteria, atomically publish its return to its own
    scratch inbox, and pass the state-bound validator before ingest:

```bash
python3 "$install_dir/tools/ledger.py" validate-return \
  --control-root "$PWD" --run-id "$run_id" \
  --attempt-id G2-COVERAGE-V5-01 \
  --return-file ".autopilot/scratch/$run_id/G2-COVERAGE-V5-01/return.json" \
  --kind review

# Substitute the current revision printed by status after validation.
python3 "$install_dir/tools/ledger.py" ingest-return \
  --control-root "$PWD" --run-id "$run_id" \
  --owner-token "$owner_token" --revision 33 \
  --attempt-id G2-COVERAGE-V5-01 \
  --return-file ".autopilot/scratch/$run_id/G2-COVERAGE-V5-01/return.json" \
  --kind review

python3 "$install_dir/tools/ledger.py" validate-return \
  --control-root "$PWD" --run-id "$run_id" \
  --attempt-id G3-PLAN-V5-01 \
  --return-file ".autopilot/scratch/$run_id/G3-PLAN-V5-01/return.json" \
  --kind review

python3 "$install_dir/tools/ledger.py" ingest-return \
  --control-root "$PWD" --run-id "$run_id" \
  --owner-token "$owner_token" --revision 34 \
  --attempt-id G3-PLAN-V5-01 \
  --return-file ".autopilot/scratch/$run_id/G3-PLAN-V5-01/return.json" \
  --kind review
```

If either verdict is BLOCK/UNVERIFIABLE, remain in the immutable DESIGN repair
cycle: stop/release both attempts, create a new bundle ID/version, publish it
against the current revision, and register new attempts on the new fingerprint.
Never alter V5, carry a historical blocker implicitly, or reuse a prior PASS.
Repeat without a fixed repair-count limit until both current-kind verdicts are
PASS or a real external blocker is recorded.

11. Once both current V5-or-later reviews are PASS, move only to PLAN and make
    the implementation hold explicit. Replace `<current-revision>` with the
    revision reported by `status --brief`; this command checks both G2 and G3
    because its next action explicitly claims the current plan gate:

```bash
python3 "$install_dir/tools/ledger.py" status \
  --control-root "$PWD" --run-id "$run_id" --brief

python3 "$install_dir/tools/ledger.py" gate \
  --control-root "$PWD" --run-id "$run_id" \
  --owner-token "$owner_token" --revision <current-revision> \
  --phase PLAN --control ACTIVE \
  --reason current_g2_g3_pass_implementation_not_authorized \
  --next-action g3_plan_pass_await_explicit_product_owner_confirmation_before_execution \
  --preconditions "current G2 coverage PASS|current G3 plan PASS|explicit product-owner confirmation before EXECUTE" \
  --read-refs "phases/plan.md,references/ledger.md"
```

Stop here. Do not transition to EXECUTE, materialize READY tickets, dispatch a
worker, create a candidate, or modify Idea Scout production code until the
product owner explicitly confirms implementation.
