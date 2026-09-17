# Codex Autopilot v1.0.7

Patch release adding the minimal auditable reconciliation path for an already
quarantined legacy repair attempt.

The new `reconcile-quarantined-attempt` command applies only to the exact
same-ticket `create → candidate → repair modify` compatibility case. It
revalidates the prior and current DONE returns, accepted blocking finding and
authorization, candidate/base/HEAD, packet scope and actual write set, then
stores an actor-attributed hash-addressed receipt and restores candidate
authority atomically. Exact retries are idempotent. Every failed proof and
every other quarantine cause remains blocked.

The schema remains `1.0` and backward-compatible through one optional attempt
receipt reference. Verification requires the complete test/qualification
suite and source/runtime package parity after installation.
