# Codex Autopilot v1.0.8

Patch release extending repair provenance for repeated same-ticket repairs of
files originally created in a create-only ticket zone.

The helper now proves every path-specific candidate/base edge back to the
original validated create, including each intervening DONE worker return,
accepted blocking finding, single-use authorization, and exact same-ticket
binding. It stores the complete lineage on the new repair attempt. The current
packet allowlist remains authoritative, and no general `modify` permission is
added to create-only zones.

Stale or forked candidates, foreign paths or tickets, broken provenance,
quarantined attempts, deny-listed paths, and chains without an original
validated create remain blocked. The schema remains `1.0`; the lineage field is
backward-compatible for existing ledgers.

Verification requires the complete test/qualification suite, a read-only dry
run against the Idea Scout revision-37 ledger, and source/runtime package parity
after installation.
