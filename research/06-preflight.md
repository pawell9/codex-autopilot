# Preflight contract

Новый Autopilot не начинает planning/dispatch, пока не зафиксировал effective environment. Это checklist требований к будущему дизайну, не runtime-код.

## Метки

`FACT` — подтверждённое; `OBSERVED` — Idea Scout V1; `INFERENCE` — вывод; `PROPOSAL` — проверка/правило V1; `OPEN` — требует эксперимента или выбора.

Сравниваемые основания: upstream [preflight](../upstream/autopilot/phases/0-preflight.md), V1 [runtime state](../references/idea-scout-v1/runtime-state/state.js) и [pause handoff](../references/idea-scout-v1/run-artifacts/2026-09-05-idea-scout/handoff-2026-09-07-wave4-pause.md), current official [config](https://learn.chatgpt.com/docs/config-file/config-basic), [subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents) и [sandbox](https://learn.chatgpt.com/docs/sandboxing).

## Результат preflight

- **PROPOSAL:** preflight создаёт один capability snapshot с timestamp, surface, repo identity, instructions, permissions, models/effort, agent concurrency, git/worktree state, tools и выбранными fallbacks.
- **PROPOSAL:** каждую проверку классифицировать `PASS / DEGRADED / BLOCKED / UNKNOWN`, с evidence и impact.
- **PROPOSAL:** `UNKNOWN` не превращать в ложный `PASS`. Если неизвестность влияет на safety/correctness — block; если только на optimisation — safe fallback.
- **PROPOSAL:** повторить preflight при resume, смене surface/profile/permissions, обновлении Codex, смене repo/worktree или material config drift.

## 1. Intent и authority

| Проверка | Evidence/result | Gate |
|---|---|---|
| Запрос действительно разрешает build/change, а не только research/review | User request + active instructions | **PROPOSAL:** без write authority — read-only path. |
| Scope, exclusions и done condition | Brief/request snapshot | **PROPOSAL:** material ambiguity → clarification либо explicit reversible assumption. |
| External/destructive/cost/data actions | Список возможных actions | **PROPOSAL:** заранее пометить authority-required, не обнаруживать это внутри non-interactive worker. |
| Source authority | Project intent vs official fact vs empirical observation vs community hypothesis | **FACT+PROPOSAL:** не смешивать роли источников. |

## 2. Workspace и repository identity

- **PROPOSAL:** resolve exact workspace root и current working directory; не использовать broad root/home как write target.
- **PROPOSAL:** определить Git root, remote/branch/HEAD, detached state, submodules и наличие nested repos.
- **PROPOSAL:** если Git отсутствует, явно выбрать degraded no-git protocol или block для workflow, требующего worktrees/commits.
- **FACT:** `codex exec` по умолчанию требует Git repo, если не задан отдельный skip flag; app worktrees также требуют Git ([Non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode), [Worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees)).
- **PROPOSAL:** зафиксировать case sensitivity/symlinks/ignored paths, если они влияют на zones/worktree contents.

## 3. Existing changes и repo health

- **PROPOSAL:** inventory staged/unstaged/untracked/ignored-relevant files без очистки или reset.
- **PROPOSAL:** считать все существующие изменения user-owned до доказательства обратного; выявить пересечение с предполагаемыми write zones.
- **PROPOSAL:** проверить in-progress merge/rebase/cherry-pick/bisect и conflicts; обычный run не стартует поверх незавершённой git operation.
- **PROPOSAL:** определить baseline tests/build только если команда известна и запуск безопасен; тяжёлый install/network не выполнять скрыто.
- **FACT:** official security guidance рекомендует clean status/feature branch/small commits, но это recommendation, не automatic guarantee ([Agent approvals & security](https://learn.chatgpt.com/docs/agent-approvals-security)).

## 4. Instruction chain

- **FACT:** Codex строит `AGENTS.md` chain один раз на run, root→CWD, closer instructions имеют precedence; default aggregate limit 32 KiB ([AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)).
- **PROPOSAL:** перечислить фактически загруженные/применимые global/project instruction files и ближайшие overrides/fallback filenames.
- **PROPOSAL:** обнаружить conflict с Autopilot contract: запрет subagents, required model, no commits, formatter/testing rules, protected paths, approval behavior.
- **PROPOSAL:** проверить truncation risk относительно `project_doc_max_bytes`; не утверждать, что worker получил инструкцию, если это не доказано.
- **PROPOSAL:** inventory selected skill scope/version/path и убедиться, что нет одноимённого shadowing.
- **FACT:** skills используют progressive disclosure, одноимённые skills не merge, repo scopes сканируются по documented chain ([Build skills](https://learn.chatgpt.com/docs/build-skills)).

## 5. Existing `.autopilot`

Определить один из случаев:

| Случай | Проверки | Действие-кандидат |
|---|---|---|
| Нет `.autopilot` | Path writable, no collision | **PROPOSAL:** new run после остальных gates. |
| Есть active run | Ledger validity, repo/base match, last checkpoint, active leases/agents/worktrees | **PROPOSAL:** resume, не overwrite. |
| Есть completed run | Version/history, новый scope | **PROPOSAL:** новый namespaced run; архивную историю не мутировать. |
| Corrupt/incomplete state | Parse/evidence/git reconstructability | **PROPOSAL:** repair state отдельно; не продолжать по догадке. |
| Run, вероятно, активен в другом session | Recent update + live agents/worktrees/process evidence | **PROPOSAL:** block concurrent ownership до adjudication; timestamp alone недостаточен. |

- **OBSERVED:** V1 подтвердил ценность reconstructible file/git state.
- **PROPOSAL:** schema/version migration никогда не выполняется неявно; old artifacts read-only до recorded migration plan.

## 6. Codex surface и version/maturity

- **PROPOSAL:** определить surface (`app`, `CLI`, `IDE`, `cloud`, non-interactive) и version/build, если доступно.
- **PROPOSAL:** features считать available только по effective runtime, а не по community config или другому surface.
- **FACT:** official pages различают local clients, ChatGPT Work и Codex cloud; model switching/worktrees/Ultra/context features доступны неодинаково ([Models](https://learn.chatgpt.com/docs/models), [Worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees)).
- **PROPOSAL:** Stable features могут быть baseline после probe; Beta/Experimental требуют explicit fallback. Permission profiles — Beta, context management — Experimental ([Feature maturity](https://learn.chatgpt.com/docs/feature-maturity)).

## 7. Models и reasoning

Зафиксировать:

- доступный model catalog именно в текущей surface/account;
- current parent model/effort;
- возможность explicit subagent override;
- available effort values per выбранной model/surface;
- review model behavior, если `/review` доступен;
- usage/limit indicators, если runtime их предоставляет;
- safe fallback class при unavailable preferred route.

- **FACT:** availability зависит от plan, rollout, sign-in и client; cloud model может быть fixed ([Models](https://learn.chatgpt.com/docs/models)).
- **FACT:** официальные страницы расходятся в `minimal/none`, `max`, `ultra` и alias `gpt-5.6`/`gpt-5.6-sol`.
- **PROPOSAL:** probe failure → inherit/current model at adequate effort or serial single-agent path; не подставлять выдуманный slug.
- **OPEN:** portable non-interactive model/effort capability endpoint в official docs не определён.

## 8. Subagents и concurrency

- **PROPOSAL:** проверить, включён ли multi-agent feature и доступны ли spawn/follow-up/wait primitives.
- **PROPOSAL:** определить effective concurrency limit, если runtime его показывает; неизвестный limit → conservative serial/low parallelism.
- **PROPOSAL:** проверить whether explicit model/effort overrides реально приняты; rejection записать как capability result.
- **PROPOSAL:** выполнить безопасный read-only smoke subagent только если будущий run действительно требует delegation; проверить return, cancellation/wait и context/instruction visibility.
- **FACT:** native subagents enabled by default в current local releases, но могут быть disabled config; default concurrency/nesting и summary schema не зафиксированы ([Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)).
- **PROPOSAL:** write-heavy parallelism не включать только потому, что threads доступны.

## 9. Sandbox, approvals и permissions

Preflight обязан зафиксировать effective, а не intended:

- sandbox mode или selected permission profile;
- writable roots и protected paths;
- approval policy/granular decisions;
- approvals reviewer/interactive availability;
- network status для shell commands;
- отдельные web/MCP/app/browser surfaces;
- child inheritance и live parent overrides;
- ability to write `.autopilot/**` и intended project zones.

- **FACT:** sandbox и approvals независимы; network default off; `.git`, `.agents`, `.codex` protected в standard workspace-write ([Agent approvals & security](https://learn.chatgpt.com/docs/agent-approvals-security)).
- **FACT:** non-interactive subagent action, которому нужен новый approval, fails и возвращает ошибку parent.
- **FACT:** custom agent `read-only` может быть изменён parent live override; это нужно проверять, не предполагать.
- **PROPOSAL:** недостаточные права → `BLOCKED` или re-plan; не обходить другой surface/tool без authority.

## 10. Git/worktree/commit capability

- **PROPOSAL:** проверить `git` executable/version, repository validity и возможность read operations.
- **PROPOSAL:** определить, кто имеет право branch/commit/worktree creation/removal и требует ли это approval.
- **PROPOSAL:** inventory existing worktrees, branches already checked out, stale locks и ignored-but-required files.
- **PROPOSAL:** если plan предполагает concurrent writes, выполнить bounded worktree smoke либо выбрать serial fallback.
- **OBSERVED:** V1 показал, что abstraction «agent isolation=worktree» недостаточна; lifecycle cleanup и background execution должны проверяться совместно.
- **PROPOSAL:** не создавать branch/worktree в preflight без фактической необходимости будущего run; здесь определяется capability и collision risk.

## 11. Tools и verification capability

- **PROPOSAL:** inventory required toolchains из repo instructions (package manager, test runner, build, formatter, browser/live environment, DB/service mocks).
- **PROPOSAL:** проверить command existence/version без install/upgrade, если это возможно.
- **PROPOSAL:** определить, какие verification oracles доступны: unit, integration, live smoke, browser/UI, mutation/negative cases, external staging.
- **OBSERVED:** green test suite V1 не обнаружила крупную потерю данных; отсутствие live oracle должно быть visible risk, не молчаливый PASS.
- **PROPOSAL:** network/install/login/paid dependency отметить как `authority-required` или `unverifiable` до ticket planning.
- **PROPOSAL:** проверить доступность read-only diff/status и средства exact changed-path audit.

## 12. Secrets и external state

- **PROPOSAL:** определить secret path patterns и required variable names без чтения values.
- **PROPOSAL:** убедиться, что task packets/state/reports не включат secret contents.
- **PROPOSAL:** перечислить операции с external side effects и sandbox/network route для них.
- **PROPOSAL:** отсутствие credentials → placeholder/unverifiable path, а не запрос вставить secret в prompt/artifact.

## Hard blockers перед run

- **PROPOSAL:** unresolved conflict с higher-priority instructions;
- **PROPOSAL:** невозможно определить workspace/repo target;
- **PROPOSAL:** active conflicting run/write lease;
- **PROPOSAL:** corrupt state, который нельзя безопасно восстановить;
- **PROPOSAL:** intended writes выходят за permission/authority boundary;
- **PROPOSAL:** destructive/external action требуется для основного пути без approval/rollback;
- **PROPOSAL:** dirty user changes пересекаются с обязательной write zone и не могут быть изолированы;
- **PROPOSAL:** acceptance невозможно определить даже как explicit `UNVERIFIABLE`.

## Degraded, но допустимые режимы

- **PROPOSAL:** no subagents → serial single-agent execution с теми же artifacts/gates;
- **PROPOSAL:** preferred model unavailable → available capability class + higher verification, записанный fallback;
- **PROPOSAL:** no worktrees → serial writers и exclusive zones;
- **PROPOSAL:** no native structured return → prose return parsed/validated orchestrator с re-request on missing fields;
- **PROPOSAL:** no live environment → статическая проверка с `UNVERIFIABLE` и user-visible acceptance gap;
- **PROPOSAL:** no dashboard/UI → state/report остаются достаточными.

## Preflight exit record

Перед следующим phase record должен ответить:

1. Какой exact target и baseline?
2. Какие instructions и user-owned changes действуют?
3. Что можно читать/писать/запускать и где нужен approval?
4. Какие agents/models/efforts фактически доступны?
5. Можно ли безопасно parallel write; если нет, какой fallback?
6. Какие tests/live oracles доступны?
7. Есть ли resumable prior run?
8. Какие неизвестности остались и почему они не блокируют?

**PROPOSAL:** отсутствие любого ответа не означает автоматический stop, но должно привести к `UNKNOWN/DEGRADED/BLOCKED`, а не к неявному предположению.
