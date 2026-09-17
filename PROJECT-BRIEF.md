# Codex Autopilot — PROJECT BRIEF

**Status:** CODEX-AUTOPILOT V1.0.9 — BLOCKED ATTEMPT CLOSURE PATCH RELEASE
**Purpose:** starting context for research and design of a Codex-native Autopilot skill
**Working project name:** `codex-autopilot`

## 1. Goal

Create a separate Codex-native version of the existing Autopilot methodology.

The goal is **not** to redesign Autopilot from scratch. The existing Autopilot has already been used successfully on a real project and its lifecycle, discipline, review model, gates, tickets, waves, interfaces, project memory, and acceptance process are considered valuable.

The target is to preserve the proven methodology where possible and redesign primarily the **execution / orchestration layer** around modern Codex capabilities.

High-level direction:

```text
Autopilot methodology
        +
Codex-native orchestration
        +
Codex subagents
        +
model / reasoning routing
        +
context isolation
        +
write-zone safety
        +
independent review
        =
CODEX AUTOPILOT
```

## 2. Why this project exists

The previous development workflow was hybrid:

```text
Claude Code orchestrator
        ↓
Codex executors
```

This worked, but created several constraints:

- the main Claude context became large and expensive;
- the workflow depended on two different agent systems;
- bridges and cross-agent handoffs added complexity;
- execution capacity was constrained by subscription/session limits;
- Codex is now capable of acting as both orchestrator and executor through native agent/subagent workflows.

The new target is:

```text
Codex orchestrator
        ↓
Codex subagents / reviewers / workers
```

Claude should no longer be a mandatory orchestration layer.

## 3. Core orchestration principle

The main Codex context is the **orchestrator**, not the universal implementation agent.

Its responsibilities should include:

- maintaining the current Autopilot state;
- reading manifest / spec / interfaces / plan;
- determining ready work;
- decomposing work into bounded tasks;
- choosing worker role;
- choosing model tier;
- choosing reasoning effort;
- checking dependencies and write zones;
- dispatching Codex subagents;
- receiving compact structured results;
- resolving blockers;
- integrating results;
- triggering review;
- escalating only when needed;
- deciding the next wave;
- maintaining project memory and checkpoints.

Routine implementation, research, inspection, and bounded fixes should normally be delegated.

## 4. Intended role split

### Codex

Codex should be the primary system for:

- orchestration;
- implementation;
- research;
- code review;
- repairs;
- acceptance workflows;
- subagent execution.

### Claude

Claude should be optional and event-driven, not continuously involved.

Potential uses:

- independent second opinion;
- high-risk architecture review;
- methodology review;
- disagreement resolution;
- selected review gates;
- final external review when justified.

Claude should **not** be required for every task, every wave, or every review cycle.

## 5. Token and limit economics

Efficient use of model/session limits is a first-class design requirement.

Key principles:

1. Do not use the strongest model for every task.
2. Use stronger reasoning/model tiers only where they materially improve outcomes.
3. Prefer bounded task packets over giving every worker the full project context.
4. Do not return full worker conversations to the orchestrator.
5. Use compact structured return contracts.
6. Keep project memory in files/state rather than relying on a single ever-growing chat.
7. Use parallelism only when tasks are truly independent and write zones do not overlap.
8. Preserve the ability to stop safely when limits are exhausted and resume from a checkpoint.

Model names and exact routing rules are **not yet fixed**. They must be derived from current Codex/OpenAI capabilities and testing.

## 6. Context isolation

A worker may consume a large local context, but the orchestrator should receive only the information required to continue.

Target return contract may include fields such as:

```text
STATUS
FILES
TESTS
INTERFACES
REQUIREMENTS
CONCERNS
BLOCKERS
COMMIT
```

The principle is:

```text
WORKER INTERNAL CONTEXT
        ↓
do not propagate
        ↓
STRUCTURED RESULT
        ↓
ORCHESTRATOR
```

This is intended to reduce orchestration context bloat and duplicated reading.

## 7. What should be preserved from existing Autopilot

The following are considered valuable unless research shows a strong reason to change them:

- project briefing;
- requirements manifest;
- specification;
- planning;
- project tiering;
- gates;
- tickets;
- dependencies;
- waves;
- write zones;
- `interfaces.md`;
- explicit contracts between tasks;
- one ticket → one fresh worker context;
- handoff/checkpoint when context grows;
- one ticket → one commit where appropriate;
- `.autopilot/state.js`;
- dashboard/state tracking;
- independent review;
- multiple review axes;
- repair flow;
- final acceptance;
- project memory;
- polish/finalisation.

The working assumption is that a large part of the original methodology can remain intact.

## 8. What likely needs redesign

The main expected redesign area is the orchestration/execution layer.

Candidate areas:

- Codex-native subagent dispatch;
- agent roles;
- model routing;
- reasoning-effort routing;
- task metadata;
- parallelism policy;
- write-zone enforcement;
- structured worker return contracts;
- reviewer lifecycle;
- escalation policy;
- repair-agent flow;
- preflight / doctor;
- Codex-specific configuration;
- checkpoint/resume behaviour;
- usage/budget awareness;
- optional telemetry for future routing improvements.

These are design targets, not yet approved implementation decisions.

## 9. Safety and ownership

The skill must follow a strict ownership principle:

> The skill owns only its own namespace. Everything else is project-owned.

Autopilot may manage its own state, e.g.:

```text
.autopilot/**
```

Project/system files are preserve-by-default, including:

```text
AGENTS.md
.claude/**
.codex/**
.github/**
.git/**
existing skills
project configuration
```

Changes outside the skill-owned namespace must be intentional and scoped.

Role-based write restrictions should be considered:

### Planning / orchestration
- read project;
- write Autopilot state/docs;
- avoid implementation edits by default.

### Executor
- read required context;
- write only assigned ticket zone and related tests.

### Reviewer
- preferably read-only.

### Repair worker
- write only the repair scope.

Destructive operations must not be available as incidental behaviour.

## 10. Preflight / doctor

Before a substantial run, the system should verify actual environment capabilities instead of assuming them.

Potential checks:

- Codex version/capabilities;
- subagent support;
- available models;
- available reasoning levels;
- per-agent model assignment;
- concurrency capability;
- git availability;
- clean/dirty working tree;
- project instructions;
- existing Autopilot state;
- unfinished prior run;
- required project tools;
- relevant Codex config.

The exact V1 scope of preflight is not yet decided.

## 11. Instruction design

The new skill should use current agent-writing principles rather than blindly copying old prompts.

Preferred direction:

- short, checkable instructions;
- explicit completion criteria;
- progressive disclosure;
- minimal always-loaded context;
- single source of truth;
- branch-specific references loaded only when needed;
- avoid unnecessary prompt sediment;
- avoid restating information that the environment can discover cheaply.

Useful conceptual structure:

```text
CONTRACT
↓
INVARIANTS
↓
CURRENT PHASE
↓
ALLOWED ACTIONS
↓
INPUT
↓
OUTPUT CONTRACT
↓
COMPLETION CRITERIA
```

Hard prohibitions should be used only where necessary; positive target behaviour is preferred where possible.

The Matt Pocock `writing-for-agents` methodology is a reference for this design process.

## 12. Real-world evidence available

The existing Autopilot was used to build **Idea Scout V1** end-to-end.

Idea Scout is now frozen as:

- version: `v1.0.0`;
- acceptance commit: `c03e78b`;
- status: `ACCEPTED V1`.

The real Autopilot run is important evidence for understanding:

- which methodology elements worked;
- where orchestration was efficient;
- where context or limits became painful;
- how executor/reviewer separation behaved;
- which rules prevented mistakes;
- where clearer boundaries were needed;
- how final review and acceptance worked in practice.

A read-only evidence bundle from Idea Scout V1 should be available in this project for analysis.

The production Idea Scout repository itself must not be modified.

## 13. Required research inputs

Before final architecture is approved, the design agent must study:

1. current upstream Autopilot implementation;
2. the real Idea Scout V1 Autopilot evidence;
3. current official OpenAI/Codex documentation;
4. current Codex subagent/custom-agent behaviour;
5. current model and reasoning options;
6. current Codex configuration and permission model;
7. current guidance for skills / `AGENTS.md`;
8. `writing-for-agents` and its skill mechanics;
9. provided GPT/Codex workspace materials as a reference, not as source of truth.

Claims from videos, community materials, old configs, or handoffs must be checked against current official documentation where relevant.

## 14. Development isolation

`codex-autopilot` must be developed in a **separate repository/project**.

Do not develop it inside Idea Scout.

Target isolation:

```text
codex-autopilot/
    ↓
research + design + implementation
    ↓
synthetic / disposable test projects
    ↓
optional disposable clone of a real project
```

Production projects are reference-only until an explicit isolated test stage.

## 15. Testing philosophy

The skill should not be first validated on Idea Scout V2.

Expected sequence:

1. static/design review;
2. synthetic/dry-run scenarios;
3. a small disposable micro-project covering the full lifecycle;
4. at least one harder/ambiguous scenario that exercises escalation/review/checkpoints;
5. optionally a disposable clone of a real project;
6. review and acceptance of the skill itself;
7. only then use it on Idea Scout V2.

Testing should evaluate both **quality** and **orchestration economics**:

- quality of decomposition;
- correctness of routing;
- duplicate work;
- context growth;
- unnecessary model escalation;
- number of repair cycles;
- parallelism quality;
- checkpoint/resume;
- review effectiveness;
- limit/token consumption where observable.

## 16. Current design status

The research/design objective is complete. V1.0.1 adds the qualified initial
intent bootstrap fix to the frozen V1 baseline after a real production run
exposed the gap. The items below are intentionally unbound runtime
choices or post-V1 extensions, not unfinished release work.

The following remain intentionally unbound or post-V1:

- exact orchestrator model;
- exact worker models;
- exact reasoning levels;
- maximum parallel workers;
- persistent vs ephemeral reviewers;
- automatic escalation rules;
- post-V1 repair-agent extensions;
- telemetry scope;
- exact Codex permission/config strategy beyond the qualified V1 path;
- exact Claude escalation gates.

Do not treat previous sketches as locked requirements.

## 17. Immediate project objective

The historical research/design objective described in this section has been
completed and released as the V1 package. The remaining material
below records the original development intent and is retained as project
provenance.

The initial implementation was deliberately not started by blindly rewriting
`SKILL.md`.

The first major deliverable should be a research/design audit that produces:

```text
KEEP
MODIFY
REWRITE
DROP
ADD
```

for the existing Autopilot components.

Then design:

- agent roles;
- model/reasoning routing;
- context contracts;
- write/filesystem safety;
- preflight;
- review/escalation policy;
- V1 scope of `codex-autopilot`.

Only after those decisions are reviewed should implementation/specification begin.

## 18. Success definition

The first version of `codex-autopilot` succeeds if it can reliably run substantial software-development workflows while:

- preserving the strong lifecycle discipline of the original Autopilot;
- using Codex as the primary orchestration system;
- delegating bounded tasks to Codex subagents;
- protecting project files and write zones;
- isolating worker context;
- keeping the main orchestration context controlled;
- routing expensive reasoning only where justified;
- reviewing independently;
- stopping and resuming safely;
- producing a clear, inspectable project state.

The objective is **not** to create a universal multi-agent platform.

The objective is a reliable Codex-native Autopilot for the user's own software projects.
