# E04a final worktree and fallback verification

## Execution-root write probe

```text
worktree app.txt: VALUE=42 -> VALUE=43
git status: M app.txt
diff: -VALUE=42 / +VALUE=43
worktree app.txt restored: VALUE=43 -> VALUE=42
post-restore tracked diff exit=0
```

The probe used only the disposable worktree. Primary foreign hashes remained
unchanged during and after it.

## Ignored state and source roots

```text
worktree-owned file=.autopilot/probe.txt
worktree status=!! .autopilot/
worktree tracked paths=README.md, app.txt
worktree root-scoped app scan=seed-repo-worktree/app.txt only
primary root-scoped app scan=seed-repo/app.txt only
primary status=?? .env; !! .autopilot/
primary tracked diff exit=0
empty-repo status=<empty>
empty-repo tracked diff exit=0
```

The shared `.git/info/exclude` applies to the worktree, but primary `.env` and
primary `.autopilot` bytes were not copied. Worktree-owned state was created
explicitly.

## Placement and persistence

```text
worktree root=/Users/pawell_9/Documents/codex-autopilot/experiments/fixtures/e04a/seed-repo-worktree
common dir=/Users/pawell_9/Documents/codex-autopilot/experiments/fixtures/e04a/seed-repo/.git
gitdir record=.../.git/worktrees/seed-repo-worktree
branch=autopilot/e04a-worktree
HEAD=362380f2574af1cd9496b9f3a4e59caa023300b0
tree=f07a5490295adaf40240fc25477c5fed2435af0f
registered in later shell commands=yes
active non-sample hooks=none
configured core.hooksPath=absent
```

Creator-process lifetime: PASS. Actual Codex UI/session-loss survival: UNKNOWN;
no session was destroyed after worktree creation.

## Runtime provenance

```text
PATH codex=codex-cli 0.153.4
active session build=UNKNOWN
git=git version 2.39.5 (Apple Git-154)
OS=macOS 15.5 arm64 (from initial qualification provenance)
permission mode=workspace-write
approval reviewer=automatic
writable root=/Users/pawell_9/Documents/codex-autopilot
outside sibling root writable=no (observed denial)
```

