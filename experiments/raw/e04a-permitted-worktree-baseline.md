# E04a permitted sibling worktree baseline

Command:

```text
git -C experiments/fixtures/e04a/seed-repo worktree add \
  -b autopilot/e04a-worktree \
  experiments/fixtures/e04a/seed-repo-worktree \
  362380f2574af1cd9496b9f3a4e59caa023300b0
```

## Raw observations

```text
exit=0
approval prompt=0
automatic review message=0
escalation=0
worktree root=/Users/pawell_9/Documents/codex-autopilot/experiments/fixtures/e04a/seed-repo-worktree
common dir=/Users/pawell_9/Documents/codex-autopilot/experiments/fixtures/e04a/seed-repo/.git
branch=autopilot/e04a-worktree
HEAD=362380f2574af1cd9496b9f3a4e59caa023300b0
tree=f07a5490295adaf40240fc25477c5fed2435af0f
status=<empty>
tracked paths=README.md, app.txt
primary .env copied=no
primary .autopilot copied=no
primary foreign hashes unchanged=yes
```

The creator command ended before later verification. Registration and files
remained visible to a separate shell command. This proves process-lifetime
persistence, not a full Codex UI/session-loss arm.

