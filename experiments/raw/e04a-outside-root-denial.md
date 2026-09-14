# E04a outside-root worktree denial

Prepared command:

```text
git -C experiments/fixtures/e04a/seed-repo worktree add --detach \
  /Users/pawell_9/Documents/codex-autopilot-e04a-worktree \
  362380f2574af1cd9496b9f3a4e59caa023300b0
```

## Raw observation

```text
exit=128
Preparing worktree (detached HEAD 362380f)
fatal: could not create leading directories of
  /Users/pawell_9/Documents/codex-autopilot-e04a-worktree/.git:
  Operation not permitted
approval prompt=0
automatic review message=0
escalation=0
alternate-tool retry=0
```

## Reconciliation

```text
outside target absent
worktree registry contains primary only
refs unchanged: autopilot/e04a-run and main only
branch/HEAD unchanged
status unchanged: ?? .env; !! .autopilot/
foreign hashes unchanged
.git/worktrees exists but contains no registered entry
```

Inference: outside-root placement is denied under the current workspace grant.
The empty administrative directory is a recorded partial Git metadata effect;
it is harmless and is not cleaned up in this qualification pass. No permission
bypass was attempted. The exact enablement condition is a session/root grant
that includes the requested sibling path and shared Git common-dir writes.

