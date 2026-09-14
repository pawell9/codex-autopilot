# Safety, writes, Git, and reviewer boundaries

The project is preserve-by-default. Canonical `.autopilot` state is orchestrator-owned; source/tests/assets/config are worker-owned only inside a versioned lease zone; Git refs/index/commits/worktrees are orchestrator actions through normal approved Git tooling. Existing `AGENTS.md`, `.agents`, `.codex`, `.claude`, skills, global config, secrets, credentials, and production data are protected unless a separate explicit scope contract says otherwise.

## Zones and audits

Zone entries are literal repo-relative files or directory subtrees with `create/modify/delete/rename` operations. Deny wins. Reject `..`, absolute allows, escaping symlinks, nested-repo/submodule mutation, unknown case-fold collisions, and undeclared formatter/codegen output. A worker writes only its lease zone plus declared disposable test scratch and exact return inbox.

Before candidate commit, resolve roots and symlink targets; compare baseline to actual Git tracked staged/unstaged changes, untracked additions/deletions, renames, bytes, file type, executable mode, relevant ignored/generated/protected paths, and foreign initial fingerprints. `files[]` is a claim, not proof. Any unexpected path quarantines the checkout and creates an ownership issue. Stage only the audited literal path list. Hooks are inspected/observed; unexpected hook mutation invalidates the candidate and requires a new audit/review.

## Git and checkout

G0 inventories the exact folder. A greenfield repository uses a recorded pre-bootstrap inventory, scoped `git init` and an initial commit of only explicitly checked seed files; `git add -A`, secret staging, reset, stash, and global identity/config edits are forbidden. An empty initial commit is the only allowed empty commit. Missing identity/hooks/permission is an exact blocker.

V1 uses a clean exclusive checkout and unique `autopilot/<run-id>` branch from the agreed committed HEAD. It never writes over user dirtiness. A dirty/busy checkout may use a qualified permanent sibling worktree outside the source tree in an already authorized root with common-dir permissions; otherwise wait for a clean checkout. Nested `.autopilot/wt` copies and managed ephemeral worktrees are not fallback. Product writers are serial; shared-checkout parallel writes are not allowed.

The worker never commits. The orchestrator audits and commits one nonempty logical candidate before review, with prepared operation containing base HEAD, intended tree, path list, operation ID, and evidence. Commit receipt includes resulting SHA/tree; history is never rewritten. `INTEGRATED` means current reviewed outcome on the run branch, not push/deploy/default-branch merge. Landing is separate explicitly authorized work.

## Ordinary review barrier

For routine coverage/plan/change review, export a pristine candidate/document view into an authorized disposable root outside the source tree. Exclude `.git`, `.autopilot`, credentials, and host state. Verify exported paths/bytes/attributes against candidate tree and list fixture/setup additions separately. Record candidate/tree/run/ledger/docs/evidence hashes in a baseline outside reviewer scratch.

The reviewer reads the frozen view and may mutate only its disposable copy/scratch for mutation tests. Stop the reviewer and its writing commands before the orchestrator independently compares candidate HEAD/tree/index/worktree, ledger/docs/evidence, protected paths, and baseline. Any mismatch invalidates the verdict and quarantines the target. This qualified routine detection/barrier does not promise OS prevention or detection of transient write-and-restore.

## Manual critical/G5 environment (D-21)

Until strict automatic transport is separately qualified, every critical axis and each G5 round uses a fresh user-assisted session with a scoped review-surface boundary: only the prepared bundle/export and the explicit reviewer mandate are transferred. The authoritative repository, control root, Git common directory, implementation history, production endpoints/state, and connectors are not transferred or used as reviewer inputs. The manual route does not claim OS-level isolation from an underlying provider host; a new CWD/worktree or native read-only label is not, by itself, either isolation proof or a reason to invent one.

The environment receipt records observable topology, accessible volumes/paths/tool connections, transferred input inventory and SHA-256 hashes, effective tool/network grants, and nonsecret probes for the declared review surface. Its `authoritative_absent` attestation means that authoritative repo/state/history and implementation narrative were absent from the declared transferred inputs and were not used; it does not require the reviewer to prove absence of unobservable host files or every system credential/environment variable. Any known authoritative project access, connector use, or credential use remains a blocker. The context receipt records new session/launch provenance where observable, exact packet/export hashes, clean-input attestation, and the absence of author/worker narrative, project-memory/chat import, fork/resume, and other project inputs. `MANUAL_ATTESTED_CLEAN` is explicit human trust about that input/context boundary, not `STRICT_FRESH` runtime proof.

The isolated reviewer can write its own test copy, not the authoritative target, and uses a pristine copy for PASS checks. Missing real integration is UNVERIFIABLE unless an explicitly sanctioned isolated oracle exists. The bundle contains no credentials or authoritative paths. External upload/provider/cost scope requires authority; the skill does not send it automatically. Returned bytes are exact structured evidence, never a script and never a reviewer repair.

During wait, the authoritative run may publish ordinary owner status/recovery transactions but the candidate and intent remain frozen. Import requires exact attempt/packet/subject/intent match, both receipts, every required criterion/axis, independent checks, and integrity evidence. Plain user sign-off never closes G5. Changed candidate/intent, missing receipt, contaminated session, known authoritative or connector access, tampered export, or mismatch blocks/quarantines the result. Unobservable host-layer properties are reported as residual trust rather than treated as strict isolation proof. The E03-M manual roundtrip is qualified at package release level; every run still requires fresh receipts and evidence.

## Effects, rollback, cleanup

Before a dangerous effect record exact target/effect, authority, current fingerprint, recoverable checkpoint or acknowledged irreversibility, effective permission, and post-effect proof. Journal commits, init/branch/worktree, landing, scoped rollback, and cleanup as prepared/applied/uncertain operations. Unknown result is quarantined; never repeat by timeout.

Partial uncommitted work may be restored only on proven owned paths with a prepared operation; foreign changes remain. A committed candidate is repaired/reverted with a new commit. No force-push, history rewrite, production migration, deployment, message, credentials rotation, recursive foreign cleanup, or remote backup is part of V1. Cleanup is optional after ownership disposition, stopped processes, and checkpoint.

**Completion:** no product effect occurs outside an authorized lease, candidate/reviewer integrity is independently checked, critical/G5 imports carry technical and context receipts, and rollback/recovery preserves foreign state.
