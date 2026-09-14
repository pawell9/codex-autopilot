# codex-autopilot

`codex-autopilot` is a Codex-native skill for taking one scoped software change
from current intent to an independently verified local Git result. The
orchestrator owns the durable ledger, routing, contracts, review flow, and
Git integration; bounded workers implement ticket-sized changes, and
independent reviewers verify them.

**CODEX-AUTOPILOT V1.0.0 — FROZEN / RELEASE READY**

## Requirements

- Codex with support for global skills and subagents.
- Python 3 (standard library only for the helper and dashboard).
- Git.

## Install as a global Codex skill

From a checkout of this repository, install the production package into the
global Codex skills directory:

```bash
install_dir="${CODEX_HOME:-$HOME/.codex}/skills/codex-autopilot"
mkdir -p "$install_dir"/{agents,contracts,dashboard,phases,references,schemas,tools}
cp SKILL.md "$install_dir/"
cp agents/openai.yaml "$install_dir/agents/"
cp contracts/reviewer.md contracts/worker.md "$install_dir/contracts/"
cp dashboard/index.html "$install_dir/dashboard/"
cp phases/{accept,design,execute,intent,plan,recover,start}.md "$install_dir/phases/"
cp references/{ledger,routing,safety}.md "$install_dir/references/"
cp schemas/contracts.schema.json "$install_dir/schemas/"
cp tools/dashboard.py tools/ledger.py "$install_dir/tools/"
```

Restart Codex after installation so the skill is discovered in a new session.
The release source package is the set of paths copied above; repository
research, design, review, experiment, and test materials are not required at
runtime.

## Start a run

Invoke the skill explicitly, for example:

```text
Use $codex-autopilot to start a scoped Git-backed software run for this task.
```

An ordinary edit does not start an Autopilot run. `start`, `resume`, `status`,
`pause`, and `cancel` are explicit skill routes.

## Presets

At the start of a run, Autopilot resolves two independent settings:

| Interaction | Depth | Meaning |
|---|---|---|
| `semi` | `normal` | Default: routine decisions proceed autonomously with existing safety gates. |
| `full` | `normal` | Removes routine interaction friction; it does not weaken safety or authority gates. |
| `semi` | `deep` | Adds more thorough analysis, alternatives, edge cases, and failure-mode coverage. |
| `full` | `deep` | Combines the full interaction mode with deep analysis. |

The default is **`semi + normal`**. Presets are stored in the run ledger,
survive pause/resume and recovery, and cannot be changed mid-run. `deep` is an
orchestration hint, not a model or lifecycle switch.

## Dashboard

The optional local dashboard is a read-only projection of the selected run
ledger. It never mutates state or controls a run:

```bash
python3 ~/.codex/skills/codex-autopilot/tools/dashboard.py \
  --control-root /path/to/repository \
  --run-id <run-id>
```

It binds to loopback by default and refreshes the current
`.autopilot/runs/<run-id>/ledger.json` projection.

## Pause and resume

Ask the skill to `pause` a run. Autopilot quiesces active work, reconciles
owned effects, and records the next safe action. Later, invoke `resume`; a
fresh orchestrator re-reads the ledger, canonical documents, and Git state
before continuing. Uncertain effects or lost handles remain recoverable or
explicitly blocked rather than being silently repeated.

## High-level lifecycle

`PREFLIGHT → INTENT → DESIGN → PLAN → EXECUTE → VERIFY → ACCEPT`

The run extracts current requirements, checks design coverage, builds a
dependency-aware plan, dispatches bounded workers, audits their write sets,
creates a candidate commit before review, performs independent verification,
and reaches `ACCEPTED` only through the required acceptance gates.

## V1 limitations

- Critical review axes and every G5 round use the qualified user-assisted
  clean-session fallback with environment/context receipts. Strict automatic
  reviewer transport is not qualified.
- V1 is serial by default. Bounded parallel worktrees (E10) remain post-V1.
- Git-backed local runs are required; scheduled/unattended operation, external
  provider dispatch, deployment, messaging, and production-data mutation are
  out of scope.
- Usage meters may be unavailable and are reported as unknown/null. Host-layer
  properties that cannot be observed are recorded as residual trust, not
  presented as strict isolation proof.
- Automatic edits to global/project instructions and legacy state migration
  are not part of V1.

## License and attribution

This repository is MIT-licensed. It includes an unchanged upstream Autopilot
copy under `upstream/autopilot/` for provenance and attribution; see
[`NOTICE.md`](NOTICE.md) and [`LICENSE`](LICENSE).

Release history is in [`CHANGELOG.md`](CHANGELOG.md).
