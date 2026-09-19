# Codex Autopilot v1.1.0

## Phase H qualification package

This release carries a reproducible qualification package under
`release-assets/v1.1.0/`. It binds the 21-file runtime install set to SHA-256
hashes, inventories and content-hashes the 33 test modules, 3 qualification
scripts, and 74 tracked fixture files, and checks the installed copy in an
isolated temporary destination.

Run the package check from the repository root:

```bash
python3 experiments/v110_release_qualification.py
python3 -m unittest tests.test_phase_h_release_parity_v110 -v
```

The check is offline and standard-library only. It fails closed on missing or
extra inventory entries, symlinks, altered source/fixture/test bytes, an
altered runtime version, conflicting replay, unsupported host tooling, or an
untested platform. The source manifest also requires the runtime set used by the
installation commands in `README.md`, including `tools/ledger.py` and the
v1.0.4 qualification packet assets.

## Runtime evidence boundary

The deterministic `FakeRuntime` covers receipt identity, event ordering,
idempotent same-byte replay, conflicting replay rejection, and descendant
stop coverage. This is a protocol/conformance model only.

Native process start, descendant enumeration, supervision, and physical stop
are explicitly **UNSUPPORTED** by this package and remain adapter-bound. A
fake receipt cannot satisfy native-runtime proof. Missing or timed-out native
observations remain `UNKNOWN`; only an exact external adapter receipt can
establish the runtime facts consumed by the ledger. No R58 production recovery
or live Idea Scout access is implied by this release artifact.

All Phase H release gates are now closed locally: Q01–Q42 pass, durable
boundary and replay qualification passes, the legacy R58 rehearsal remains
read-only/copy-only, source/runtime package parity passes, and the independent
diff/state-machine review is PASS. The final repository discovery run completed
`260 tests in 1106.828s, OK, skipped=1`; the one skip is the documented opt-in
production-checkpoint audit. This is release readiness for the committed local
candidate, not evidence that a tag was created, a push occurred, or live R58
state was resumed.
