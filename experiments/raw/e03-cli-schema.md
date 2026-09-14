# E03 CLI transport schema discovery

Raw command set:

```text
codex exec --help
codex review --help
codex exec review --help
```

Observed PATH CLI: `codex-cli 0.153.4`.

Relevant exposed options from `codex exec`:

```text
-s, --sandbox <read-only|workspace-write|danger-full-access>
--approve-for-me
-C, --cd <DIR>
--add-dir <DIR>
--skip-git-repo-check
--ephemeral
--ignore-user-config
--ignore-rules
--output-schema <FILE>
-o, --output-last-message <FILE>
--json
-m, --model <MODEL>
```

`codex exec review` exposes commit/base/uncommitted selection plus model,
ephemeral, ignore-user-config/rules, output-schema, output-last-message and JSON
events. The active collaboration tool schema exposes no slash-command review
entry point and no custom agent sandbox/config constructor.

