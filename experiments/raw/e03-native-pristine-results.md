# E03 pristine native review and barrier

## Raw reviewer return

```text
subject=experiments/fixtures/e03/export-native-pristine/app.txt
observed=VALUE=41\n
expected=VALUE=42\n
observed hex=56 41 4c 55 45 3d 34 31 0a
verdict=BLOCK
```

## Independent post-stop barrier

```text
HEAD=5632eb4182aa896d37e5b3648014e867d05509c5
git status porcelain=<empty>
all candidate/state baseline hashes unchanged
export app hash=3afd031f89bc75bdafff838635fdbc4708b4b079d51306c3d97636e2fc45b35a
```

The message verdict is usable for this exact subject/mandate because the
reviewer stopped and the independent barrier passed.

