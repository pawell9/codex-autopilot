# Codex Autopilot v1.1.1

Release date: 2026-09-21
Type: backward-compatible lifecycle patch
Compatibility floor: schema 1.0 / prior creation releases preserved

This patch contains only generic lifecycle corrections exercised while
completing Idea Scout T02. It does not change Idea Scout product code, source
fixtures, or run artifacts.

The patch adds exact Git initialization/bootstrap binding, replacement-ticket
checkpoint validation, fresh review routing after repair, control-file-aware
write-set auditing, amendment hash preservation, and guarded manual-G5 and
stale-lease recovery. Every retained behavior has focused regression coverage,
including idempotent replay and fail-closed fence/proof rejection.

Qualification package: `release-assets/v1.1.1/`.

```bash
python3 experiments/v111_release_qualification.py
python3 -m unittest tests.test_phase_h_release_parity_v111 -v
```
