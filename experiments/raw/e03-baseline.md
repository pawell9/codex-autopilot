# E03 independent baseline before reviewers

```text
candidate commit=5632eb4182aa896d37e5b3648014e867d05509c5
candidate tree=711d4f7167d9bd90c6c6c2e7d5a16871483cc92a
git status porcelain=<empty>
authoritative app.txt sha256=3afd031f89bc75bdafff838635fdbc4708b4b079d51306c3d97636e2fc45b35a
authoritative sentinel.txt sha256=9c7b84d3f60ccb8d6c0991e9861fd1a75f4a052ccac9e4651e0262e24f5b8fa1
authoritative restore-sentinel.txt sha256=778c9b71233e1ac0fc2fc57b6ba6d18baece773c44bafef20c70ac722e205159
state ledger-sentinel.txt sha256=ae6208dd9e177bdb05a45f1722c8479ec97762b59ede724ea250fe9ac8ef6ca2
native export diff versus committed worktree excluding .git=<empty>
CLI export diff versus committed worktree excluding .git=<empty>
```

Both exports were produced independently with `git archive HEAD`. Neither
contains `.git` or `.autopilot`.

