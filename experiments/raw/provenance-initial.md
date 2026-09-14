# Initial runtime/build provenance

Observed 2026-09-12 in `/Users/pawell_9/Documents/codex-autopilot`.

## Raw observations

```text
cwd=/Users/pawell_9/Documents/codex-autopilot
PATH codex=/Users/pawell_9/.nvm/versions/node/v22.22.2/bin/codex
codex --version=codex-cli 0.153.4
git=/usr/bin/git
git --version=git version 2.39.5 (Apple Git-154)
macOS ProductVersion=15.5 BuildVersion=24F74
architecture=arm64
python=Python 3.14.7
workspace root is not a Git repository
```

## Provenance limits

- The PATH CLI version is not proof of the active ChatGPT/Codex session build.
- Active session build/model identity is not exposed by the current tool
  envelope, so those fields remain UNKNOWN unless an experiment produces a
  stronger receipt.
- The active orchestration interface exposes native agent controls
  `spawn_agent`, `send_message`, `followup_task`, `interrupt_agent`,
  `list_agents`, and `wait_agent`. `spawn_agent` exposes task name, message,
  context fork selection, optional agent type, model, and reasoning effort;
  it does not expose an observed child model receipt.
- Effective filesystem policy for this session is workspace-write with the
  project root and temporary roots writable; `.git`, `.agents`, and `.codex`
  are protected/read-only absent a reviewed escalation. Network is restricted.
- Approval reviewer is automatic. No reusable broad Git permission is assumed.

