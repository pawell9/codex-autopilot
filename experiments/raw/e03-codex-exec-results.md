# E03 `codex exec` read-only process arm

## Attempt 1 — outer sandbox

```text
command exit=1
failed to open /Users/pawell_9/.codex/logs_2.sqlite: readonly database
failed to initialize in-process app-server client: Operation not permitted
```

This attempt did not start a reviewer and is not an isolation verdict.

## Attempt 2 — approved outer execution, inner read-only retained

The exact command retained:

```text
--sandbox read-only
--ephemeral
--ignore-user-config
-C experiments/fixtures/e03/export-cli
--skip-git-repo-check
--output-schema experiments/fixtures/e03/packet/review-output.schema.json
--output-last-message experiments/fixtures/e03/returns/codex-exec.json
--json
```

Raw terminal events:

```text
thread.started thread_id=01a0971d-15ca-7601-a20d-d90976f14d90
turn.started
websocket sampling: 401 Unauthorized, Missing bearer or basic authentication
fallback HTTPS sampling: 401 Unauthorized, Missing bearer or basic authentication
turn.failed
command exit=1
codex login status=Not logged in
```

The process also attempted plugin cache sync and reported an existing lock plus
network authorization/rate-limit warnings. No config/cache cleanup was
performed because that would exceed the experiment scope.

## Post-failure observations

```text
structured output file absent
export mutation file absent
authoritative sentinel hash unchanged
state sentinel hash unchanged
export app hash unchanged
authoritative git status=<empty>
```

Verdict: **UNKNOWN / unavailable on this account state**, not PASS and not an
inner read-only enforcement result. Authentication/setup is the exact resume
condition; global config or credential changes were not attempted.

