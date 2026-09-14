# Safety and write policy

Документ отделяет технические гарантии Codex от правил, которые обязан обеспечивать Autopilot instruction/state layer. Реализация guards здесь не создаётся.

## Метки

`FACT` — подтверждённая гарантия/ограничение; `OBSERVED` — V1; `INFERENCE` — вывод; `PROPOSAL` — политика-кандидат; `OPEN` — требует проверки.

Empirical anchors: [project agent rules](../references/idea-scout-v1/agent-rules/AGENTS.md), [executor boundaries](../references/idea-scout-v1/agent-rules/docs/executor.md), [review log](../references/idea-scout-v1/run-artifacts/2026-09-05-idea-scout/review-log.md) и [git history](../references/idea-scout-v1/git-log-oneline.txt).

## Два слоя безопасности

| Слой | Что может гарантировать | Чего не гарантирует |
|---|---|---|
| Codex runtime: sandbox, approvals, execpolicy, protected paths | **FACT:** ограничение write roots/network, запрос approval, запрет/разрешение command prefixes, защита `.git`/`.agents`/`.codex` в стандартном `workspace-write`. | **FACT:** не знает ticket ownership, intent пользователя, requirement scope или кто должен редактировать обычный project file. |
| Autopilot policy: packets, zones, state, review, git protocol | **PROPOSAL:** semantic ownership, declared changes, role separation, safe sequencing, evidence gates. | **INFERENCE:** instruction-only правило может быть нарушено моделью или bypassed tool; требуется независимая проверка actual effects. |

Источники: [Sandbox](https://learn.chatgpt.com/docs/sandboxing), [Agent approvals & security](https://learn.chatgpt.com/docs/agent-approvals-security), [Rules](https://learn.chatgpt.com/docs/agent-configuration/rules), [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents#approvals-and-sandbox-controls).

## Ownership файлов

### Базовые классы

| Класс | Примеры | Default owner | Политика |
|---|---|---|---|
| Autopilot-owned run state | `.autopilot/**` | Orchestrator | **PROPOSAL:** единственная зона, которую методология может создавать/обновлять без отдельного product ticket. |
| Project-owned source/tests/assets/docs | Всё вне `.autopilot/**`, включая `src/`, `tests/`, `docs/` | Назначенный worker ticket | **PROPOSAL:** preserve-by-default; только declared write zone и requirement. |
| Project instruction/config | `AGENTS.md`, `AGENTS.override.md`, `.codex/**`, `.agents/**`, `CLAUDE.md` | Пользователь/проект | **FACT+PROPOSAL:** не менять скрыто. Отдельная явная задача и approval; часть путей runtime уже protected. |
| Git metadata/history | `.git/**`, branches, index, commits/tags | Integration protocol/user authority | **FACT:** `.git` protected в `workspace-write`; app/shell git paths могут иметь разные approval flows. **PROPOSAL:** операции только на resolved repo/worktree и объявленном checkpoint. |
| Secrets/external credentials | `.env*`, secret stores, keys/tokens | Пользователь/runtime secret mechanism | **PROPOSAL:** никогда не читать/копировать без явной необходимости и authority; никогда не писать значения в artifacts/logs. |
| External state | DB, cloud, messages, deploy, paid APIs | Пользователь/explicit task owner | **PROPOSAL:** отдельная authority boundary; dry/local alternative по умолчанию. |

- **FACT:** project brief разрешает Autopilot владеть `.autopilot/**` и требует сохранять project-owned files.
- **OBSERVED:** upstream/used пытался автоматически поддерживать `CLAUDE.md`/`AGENTS.md`; это конфликтует с preserve-by-default для Codex-native V1.
- **PROPOSAL:** изменение durable project docs может быть полезным deliverable, но должно появляться как отдельный ticket с видимым diff, не как финальный side effect.

## Write zones

Каждый write ticket до spawn фиксирует:

- exact allow paths/patterns;
- explicit deny/shared paths;
- owner и lifetime lease;
- base revision/worktree;
- допустимы ли creates/deletes/renames;
- ожидаемый write set;
- integration order и conflict policy.

- **PROPOSAL:** зона exclusive, пока ticket `in-progress/review/repair`; пересечение writers запрещено, если это не один сериализованный owner.
- **PROPOSAL:** worker может читать за пределами зоны, если sandbox/secret policy разрешает, но не писать.
- **PROPOSAL:** необходимость нового path → `BLOCKED: WRITE_ZONE_MISSING`, а не silent expansion.
- **PROPOSAL:** перед review orchestrator сравнивает actual changed paths с allow set; undeclared path блокирует integration независимо от качества кода.
- **OBSERVED:** Idea Scout plan review нашёл overlap `.env.example`; поздние fixes требовали formal amendments для shared surfaces.

## Политика по ролям

### Orchestrator

- **PROPOSAL:** пишет только `.autopilot/**` и выполняет механические, заранее объявленные integration operations.
- **PROPOSAL:** не применяет product fix, найденный reviewer; создаёт repair packet.
- **PROPOSAL:** не меняет requirements/interfaces задним числом без amendment с cause/evidence.
- **PROPOSAL:** перед любым parallel dispatch проверяет disjoint zones или isolated worktrees.

### Executor / worker

- **PROPOSAL:** writes only `write_allow`; no git history mutations unless packet explicitly assigns them.
- **PROPOSAL:** не меняет `.autopilot`, project instructions, tool configs, secrets, lockfiles или generated files, если они не перечислены.
- **PROPOSAL:** destructive migration/delete/rename требует отдельного флага и rollback proof.
- **PROPOSAL:** возвращает полный `changed_paths`, но orchestrator доверяет VCS/filesystem evidence, не только self-report.

### Reviewer

- **FACT:** native `/review` не меняет working tree; custom agent может быть configured read-only ([Code review](https://learn.chatgpt.com/docs/code-review)).
- **FACT:** parent live permission override может быть повторно применён к subagent, поэтому read-only custom config не абсолютная гарантия.
- **PROPOSAL:** effective read-only проверяется при preflight/spawn; reviewer instructions всё равно запрещают write. Если технический read-only недоступен — reviewer получает clean snapshot/worktree и post-check zero diff.

### Repair

- **PROPOSAL:** наследует не «все файлы original ticket», а минимальный write set конкретных findings.
- **PROPOSAL:** contract repair и code repair не смешиваются в одном незаметном действии.
- **PROPOSAL:** regression test/proof входит в write scope; unrelated cleanup запрещён.

## Защита project-owned файлов

- **PROPOSAL:** preflight строит protected set из user instructions, repository conventions, dirty files, configs, secrets patterns и Autopilot defaults.
- **PROPOSAL:** существующие user changes считаются чужими; ticket не должен revert/format/rewrite их без явного включения.
- **PROPOSAL:** broad formatter/codegen разрешён только после dry/list mode либо на явно scoped paths; actual diff проверяется.
- **PROPOSAL:** overwrite whole file допустим только когда tool semantics этого требуют и base hash совпадает; иначе patch/edit.
- **PROPOSAL:** generated/vendor/build outputs по умолчанию не коммитятся и не используются как source of truth.

## Destructive operations

К destructive относятся delete/recursive clean, history rewrite, force push, reset, dropping data/schema, overwriting external state, credential rotation и irreversible deployment.

Перед действием обязателен gate:

1. **PROPOSAL:** exact resolved target, без unresolved broad env/glob.
2. **PROPOSAL:** действие прямо следует из user request или получено отдельное approval.
3. **PROPOSAL:** проверены current state и recoverable alternative.
4. **PROPOSAL:** существует rollback/backup/checkpoint либо явно зафиксирована необратимость.
5. **PROPOSAL:** sandbox/approval/execpolicy позволяют именно это действие.
6. **PROPOSAL:** после действия проверен actual effect и сообщена recoverability.

- **FACT:** sandbox и approvals независимы; `danger-full-access` снимает важную границу и не должен быть default ([Sandbox](https://learn.chatgpt.com/docs/sandboxing)).
- **FACT:** execpolicy умеет `allow/prompt/forbidden`, но сложные shell wrappers проверяются иначе, чем простые цепочки; это не semantic parser всех destructive intentions ([Rules](https://learn.chatgpt.com/docs/agent-configuration/rules)).
- **PROPOSAL:** destructive guard не строить только на string matching community `guard-rm.sh`; это полезная hypothesis, не доказанная полная защита.

## Worktrees, branches, commits

### Подтверждённое

- **FACT:** worktrees дают independent working trees с общей Git metadata; один branch нельзя одновременно checkout в двух worktrees ([Worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees)).
- **FACT:** Codex-managed app worktree стартует detached и связан с chat; ignored files обычно не переносятся.
- **OBSERVED:** Idea Scout agent-managed background worktree был очищен слишком рано; explicit orchestrator-created worktrees оказались надёжнее в том конкретном bridge.
- **OBSERVED:** frequent ticket/checkpoint commits сделали resume и rollback practicable.

### V1 policy candidate

- **PROPOSAL:** read-only agents не получают worktree без практической необходимости.
- **PROPOSAL:** один concurrent write ticket — один explicit isolated worktree либо доказанно disjoint write zone в общей tree; default для неизвестного runtime — serial writes.
- **PROPOSAL:** orchestrator records base commit/worktree path/branch state before spawn.
- **PROPOSAL:** worker не создаёт/удаляет branch/worktree и не commit/push без assigned ownership.
- **PROPOSAL:** один verified logical outcome — один recoverable checkpoint; «one ticket = one commit» предпочтение, но не догма для no-git или user-owned commit policy.
- **PROPOSAL:** integration проверяет base drift, actual diff, tests, zone and review before commit/merge.
- **PROPOSAL:** conflicts не разрешаются механически orchestrator, если требуют продуктового решения; создаётся repair/integration ticket.
- **OPEN:** нужен runtime experiment, какой worktree mechanism одинаково надёжен в app/CLI/IDE и при native subagents.

## Sandbox и permissions

| Capability | Codex guarantee | Autopilot obligation |
|---|---|---|
| Workspace boundary | **FACT:** `workspace-write` ограничивает записи configured roots; network default off. | **PROPOSAL:** проверить effective roots/mode; не предполагать default. |
| Protected internals | **FACT:** `.git`, `.agents`, `.codex` protected recursively в standard workspace-write. | **PROPOSAL:** не обещать mutation этих путей; отдельный approval/action при необходимости. |
| Approvals | **FACT:** отдельны от sandbox; non-interactive agent не может сам получить новый approval. | **PROPOSAL:** предвидеть permission needs до dispatch; permission failure не repair моделью. |
| Permission profiles | **FACT:** granular filesystem/network, но Beta и не композируются с legacy sandbox mode. | **PROPOSAL:** optional hardening с version gate/fallback, не V1 dependency. |
| Network | **FACT:** domain enforcement требует network proxy; MCP/web/app surfaces могут иметь отдельные controls. | **PROPOSAL:** inventory каждой surface; не считать shell network policy общей. |
| Subagent inheritance | **FACT:** наследует parent runtime policy; live overrides могут reapply. | **PROPOSAL:** записать effective child policy и post-check writes. |
| Logical file zones | **FACT:** не предоставляются автоматически. | **PROPOSAL:** packet + lease + actual diff validation. |
| User intent/scope | Не runtime capability. | **PROPOSAL:** requirement/authority gates. |

## Failure policy

- **PROPOSAL:** sandbox/approval denial → `BLOCKED: PERMISSION`, без обхода альтернативным tool/shell.
- **PROPOSAL:** write-zone violation → остановить integration, сохранить evidence, fresh repair; не «починить diff» молча.
- **PROPOSAL:** обнаруженный secret exposure → прекратить дальнейшее распространение, не печатать value, сообщить path/type и запросить incident action.
- **PROPOSAL:** unexpected dirty state → не clean/reset; определить owner и исключить/serialise conflict.
- **PROPOSAL:** worktree cleanup возможен только после recorded integration/abandon decision и exact target validation.

## Незакрыто

- **OPEN:** использовать ли Beta permission profiles как optional hardening уже в V1.
- **OPEN:** точный git commit/branch ownership по разным Codex surfaces.
- **OPEN:** формат и атомарность write-zone lease/actual-write verifier.
- **OPEN:** какие project instruction/doc changes пользователь хочет разрешать Autopilot автоматически; текущий brief указывает preserve-by-default.
