# E04a — Git approvals, bootstrap, and worktree placement

Overall verdict: **PASS** for the required pre-implementation Git capability.
A viable authorized local Git flow exists with known current-session approval
cost. Selected V1 checkout mode is **clean exclusive checkout**. Permanent
sibling worktree placement passed only inside an already-authorized parent
root; it remains conditional and is not the default because true session-loss
survival and workspace-root sibling authority are not qualified.

## Provenance and effective permissions

- PATH CLI: `codex-cli 0.153.4`; active session build: **UNKNOWN**.
- Git: `2.39.5 (Apple Git-154)`; macOS 15.5 arm64.
- Effective session policy: workspace-write under
  `/Users/pawell_9/Documents/codex-autopilot`; approval reviewer automatic.
- Global Git identity and global `core.hooksPath` were absent. Fixture commits
  used per-command disposable identity; no global or persistent local identity
  was written. A real target without identity remains an exact setup blocker.
- Active non-sample hooks in the seed fixture: none.

Raw checkpoints: [plan](raw/e04a-plan-checkpoint.md),
[bootstrap/commits](raw/e04a-bootstrap-and-commits-partial.md), and
[resume reconciliation](raw/e04a-resume-reconciliation.md).

## Qualification matrix

| Arm | Verdict | Raw observation | Inference / limitation |
|---|---|---|---|
| Parent/nested-repo guard | PASS | Both greenfield folders returned Git probe exit 128 before init | No accidental parent repository was captured |
| Empty greenfield bootstrap | PASS | Empty initial commit `01b5c4c`, empty tree `4b825dc` | Git-required flow can establish an empty baseline |
| Seed bootstrap / secret exclusion | PASS | Only `README.md` and `app.txt` staged; `.env` stayed untracked and absent from tree `91f306f` | Exact path staging works; the seed primary checkout is intentionally not clean-exclusive |
| Unknown existing folder | PASS (safe block) | `unknown-existing/foreign.txt` inventoried; no Git init | Ownership decision is required before bootstrap |
| Git identity handling | PASS for detection; real identity setup UNKNOWN | Global identity absent; fixture-only `-c` identity produced commits and did not persist | V1 must block for user identity/setup, not invent production authorship |
| Local exclude | PASS | Existing bytes preserved; one `.autopilot/` line appended; owned state reported ignored | Exclude is not backup; destructive stash/clean behavior is E04b and was not run |
| Run branch | PASS | `autopilot/e04a-run` created from seed baseline | Unique local branch action available |
| Candidate before review | PASS | Candidate `38297af` existed before observation of `VALUE=41` | Commit timing matches design; commit was not called INTEGRATED |
| Repair commit | PASS | Repair `362380f` produced `VALUE=42`; history not rewritten | Separate repair commit available |
| In-root Git approvals | PASS | 11 mutating Git commands succeeded with 0 prompts, 0 automatic-review messages, 0 escalations | Current writable-root cost is known; it is fingerprint-specific |
| Outside-root denial | PASS | Detached worktree attempt exit 128 `Operation not permitted`; no target/ref/registration; one empty admin directory remained | Denial was not bypassed; exact enablement is a sibling-root grant plus common-dir authority |
| Reusable prefix | UNKNOWN / unused | No prefix requested or exposed as necessary | No blanket Git permission may be inferred |
| Permitted sibling placement | PASS for current nested-root topology | Dedicated root/branch at `362380f`; common-dir points to primary `.git` | Applies when an authorized writable parent contains both siblings |
| Execution-root writes | PASS | Worktree `app.txt` changed, appeared as exact diff, and restored clean | Worktree source writes are available in the granted root |
| Shared `.git` writes | PASS | Worktree registration/ref/index created in primary common-dir | Creation needs both execution-root and common-dir permission |
| Ignored/source scan | PASS | Worktree-owned `.autopilot` ignored; `.env` not copied; each repo-root scan found one `app.txt` | Root must be exact; scanning the wider experiment parent would see both siblings |
| Creator-process persistence | PASS | Later independent shell commands saw worktree registration and files | Permanent Git registration is not tied to creator command |
| Full Codex session-loss persistence | UNKNOWN | No post-creation UI/session destruction was performed | Keep worktree conditional until a real resume arm confirms it |
| Clean-checkout fallback | PASS | Empty fixture remained fully clean; primary tracked trees remained clean; clean-only policy has exact user action when foreign dirt exists | For a dirty real checkout, user must free it unless a matching sibling topology is qualified |

## Approval and effect accounting

```text
mutating Git commands attempted=12
mutating Git commands succeeded=11
Git commands denied=1 (outside-root worktree)
approval prompts=0
automatic-review messages=0
escalations=0
reusable-prefix requests=0
alternate-tool attempts after denial=0
scoped raw Git-metadata effects=1 (.git/info/exclude via apply_patch)
```

The successful commands were two init operations, two initial commits, three
exact `git add` operations, branch creation, candidate commit, repair commit,
and permitted worktree creation. Read-only Git probes are not included. The
denied worktree attempt is detailed in
[outside-root denial](raw/e04a-outside-root-denial.md); permitted placement and
final checks are in [baseline](raw/e04a-permitted-worktree-baseline.md) and
[verification](raw/e04a-final-verification.md).

## Selected strategy for V1

1. Use native Git commands at the normal approval boundary with exact `-C`,
   expected HEAD/tree and literal staged paths. Keep approval counts as runtime
   facts; request no blanket Git prefix.
2. Bootstrap only empty or explicitly adjudicated seed folders. Empty baseline
   commit is allowed; seed baseline uses an inspected file list. Unknown files,
   credentials and existing staged state block until scoped.
3. Treat missing author identity or active hooks as exact setup facts. Preserve
   hooks and user config; do not write global identity.
4. Default to a clean exclusive checkout. Existing foreign untracked files make
   that checkout ineligible even if exact staging would avoid them.
5. Enable permanent sibling worktrees only when both the sibling root and shared
   common-dir writes are already authorized and match this topology. For the
   workspace-root project geometry tested here, the natural outside sibling was
   denied, so clean-only remains the selected fallback.

## Remaining checks

- Repeat worktree observation across a real Codex session loss before promoting
  it from conditional placement to fully qualified recovery authority.
- E04b must later test hooks, foreign dirt, symlinks, stash/clean limitations and
  crash reconciliation after the runtime helper exists. It was not run here.

