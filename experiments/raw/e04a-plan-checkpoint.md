# E04a pre-effect checkpoint

Authorized fixture roots:

```text
experiments/fixtures/e04a/empty-repo
experiments/fixtures/e04a/seed-repo
experiments/fixtures/e04a/seed-repo-worktree
experiments/fixtures/e04a/unknown-existing (inventory only; no Git init)
```

Deliberately unauthorized sibling probe:

```text
/Users/pawell_9/Documents/codex-autopilot-e04a-worktree
```

Planned effects in order:

1. Inventory parent Git identity and every seed entry.
2. Empty repo: init, local per-command identity, empty initial commit.
3. Seed repo: init; stage only `README.md` and `app.txt`; initial commit;
   verify `.env` remains untracked and absent from tree.
4. Add exact `.autopilot/` line to seed repo local exclude, preserving bytes;
   create owned ignored fixture and verify status.
5. Create `autopilot/e04a-run`; candidate commit before review observation;
   repair commit afterward.
6. Attempt unauthorized outside-root detached worktree once. On denial inspect
   path, worktree registry and refs; do not retry/escalate.
7. Create permitted permanent sibling `seed-repo-worktree` on a dedicated
   branch, verify common-dir/root/source scan, then verify it in a later command.

No stash, clean, reset, hooks change, global config, push, merge, or removal is
planned. E04b actions are excluded.

