# Codex Autopilot v1.0.9

Patch release adding the normal lifecycle exit for a repair worker that returns
`BLOCKED` before its first write while retaining an active lease and no
candidate.

`close-blocked-attempt` (alias `restore-last-validated-candidate`) is limited to
the exact current returned worker repair on a BLOCKED ticket/run. It validates
the stored BLOCKED return and empty file declaration, rejects any candidate or
unresolved effect, derives the immediate prior validated same-ticket candidate,
and proves the checkout HEAD, tree, and complete write-set still equal that
base. The command accepts no candidate selector.

On success it releases the blocked attempt lease, appends a hash-addressed
closure receipt plus decision/evidence records, and restores only the ticket's
current-candidate linkage. All attempts and returns remain in history. The
ticket remains BLOCKED until a fresh changed `authorize-repair` decision starts
the ordinary next repair cycle.

Verification requires positive, idempotent, follow-on-cycle, and negative
regressions; the complete test/qualification suite; a read-only-copy dry run
against the Idea Scout revision-47 state; and source/runtime package parity
after installation.
