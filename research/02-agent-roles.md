# Agent roles: проектные основания

Документ определяет responsibilities и boundaries, но не TOML/custom-agent configs и не runtime implementation.

## Метки

`FACT` — официально/проектно подтверждено; `OBSERVED` — Idea Scout V1; `INFERENCE` — вывод; `PROPOSAL` — кандидат следующего design-pass; `OPEN` — требуется решение/эксперимент.

Ключевые empirical anchors: [review log](../references/idea-scout-v1/run-artifacts/2026-09-05-idea-scout/review-log.md), [final state](../references/idea-scout-v1/runtime-state/state.js), [executor rules](../references/idea-scout-v1/agent-rules/docs/executor.md) и [resume handoff](../references/idea-scout-v1/run-artifacts/2026-09-05-idea-scout/handoff-2026-09-07-wave4-pause.md).

## Принцип топологии

- **FACT:** Codex имеет built-in `default`, `worker`, `explorer`, умеет запускать отдельные subagent threads и возвращать summaries; custom roles возможны, но их формат может эволюционировать ([Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)).
- **OBSERVED:** в V1 устойчивой оказалась не identity процесса, а его мандат и записанный checkpoint. Reviewer handles не пережили остановку; review continuity восстановили из файлов.
- **PROPOSAL:** различать **логическую роль** и **живой agent thread**. Роль может жить весь run; thread по умолчанию disposable и восстанавливается из task packet/checkpoint.
- **PROPOSAL:** минимальное ядро ролей V1: orchestrator, worker, reviewer, researcher, repair и blind acceptance verifier. Отдельный planner/integrator/security-agent не является обязательным типом агента; это мандаты существующих ролей.

## Матрица ролей

| Роль | Ответственность | Допустимые действия | Write ownership | Lifetime/context | Взаимодействие |
|---|---|---|---|---|---|
| **Orchestrator** | Сохраняет intent, requirement ledger, state machine, dependencies, routing, gates, user decisions и итоговый report. | Read repo/evidence; создавать task packets; spawn/wait/steer; валидировать returns; запускать независимые проверки; обновлять owned run-state; выполнять согласованные git integration operations. | **PROPOSAL:** только `.autopilot/**` и явно объявленные integration metadata. Не чинит product code «за worker». Project-owned docs — только как отдельный user-approved deliverable. | **PROPOSAL:** логически постоянен на run; контекст регулярно сжимается до durable checkpoint. Thread можно заменить без потери состояния. | Dispatch к worker/researcher/reviewer; adjudicates BLOCKED и disagreement; обращается к пользователю только на material authority forks. |
| **Worker / executor** | Реализует один проверяемый ticket/result slice. | Читать нужный repo context; менять только declared zones; писать/обновлять тесты; запускать scoped checks; возвращать evidence или `BLOCKED`. | **PROPOSAL:** exclusive declared write set; shared files только через заранее назначенного owner или serialized ticket. Не пишет `.autopilot/**`, если не назначен отдельный adapter contract. | **PROPOSAL:** fresh context на ticket. Follow-up в том же thread только для узкого implementation repair при сохранённой релевантности. | Получает immutable task packet; возвращает structured result; не меняет контракт самостоятельно. |
| **Reviewer** | Независимо проверяет один мандат: spec/requirements, correctness/craft, security, UX или integration. | Читать diff/changed files/contracts; запускать проверки; приводить file:line/command evidence; выдавать PASS/BLOCK/OPEN. | **PROPOSAL:** none. Read-only должен подтверждаться effective sandbox; instruction-only запрет — defense-in-depth. | **PROPOSAL:** fresh на review unit, если нужен independence; cross-ticket continuity хранить в reviewer ledger, а не в handle. | Не repair. Findings идут orchestrator; re-review получает findings+new evidence, но не narrative защиты исполнителя. |
| **Researcher / explorer** | Закрывает конкретную неизвестность: codebase fact, API/docs fact, reproduction, compatibility. | Read-only search/inspection; минимальные non-mutating probes; primary-source citations; разделять fact/inference. | **PROPOSAL:** none, кроме явно запрошенного research artifact внутри выделенной зоны. Для runtime-разведки — no write. | **PROPOSAL:** fresh и узкий вопрос; завершает работу после evidence ledger. | Возвращает fact, source, uncertainty, impact; не принимает продуктовые решения за orchestrator/user. |
| **Repair executor** | Исправляет подтверждённый дефект без расширения scope. Это режим исполнения, не обязательно отдельный custom agent type. | Изменять назначенные zones, добавлять regression proof, запускать focused+relevant suite. | **PROPOSAL:** write set исходного ticket либо новый явно согласованный set; contract repair отдельно от code repair. | **PROPOSAL:** same worker для локального underdone; fresh worker при stuck/repeated class/context saturation; stronger model только после cause triage. | Получает finding IDs и acceptance evidence; не получает необязательный review chatter; возвращает mapping finding→proof. |
| **Blind acceptance verifier** | Проверяет observable product against current brief без внутренних оправданий реализации. | Читать brief и repo; запускать продукт/critical scenarios; фиксировать fulfilled/partial/missing/unverifiable. | **PROPOSAL:** none. | **PROPOSAL:** всегда fresh; не видел spec, manifest, tickets, repair history. | Возвращает requirement-level verdict; defect отправляется в новый repair ticket, verifier не исправляет. |
| **User / decision authority** | Определяет intent и даёт новую authority там, где действие меняет продукт/риск/внешнее состояние. | Принимать/отклонять material scope, destructive/data/external/cost/access decisions. | Project-wide по собственному решению. | Вне agent lifecycle. | Orchestrator приносит минимально достаточный вопрос с вариантами/evidence. |

## Роль orchestrator

### Что сохраняется

- **OBSERVED:** V1 требовал единого владельца manifest/spec amendments, zones, wave state, review routing и integration.
- **PROPOSAL:** orchestrator — единственный writer durable orchestration ledger и единственный adjudicator изменений контракта.
- **PROPOSAL:** его deliverable — доказанная завершённость, а не объём собственных code changes.

### Чего orchestrator не делает

- **PROPOSAL:** не исправляет product code между ticket return и review, иначе исчезают ownership, независимость и traceability.
- **PROPOSAL:** не «лечит» `BLOCKED` добавлением неявного разрешения; сначала классифицирует contract/environment/permission/implementation cause.
- **PROPOSAL:** не хранит критическое состояние только в chat, agent handle или скрытой памяти.
- **FACT:** goal/agent features не расширяют sandbox или approvals ([Long-running work](https://learn.chatgpt.com/docs/long-running-work)). Orchestrator не может обещать worker полномочия, которых нет в effective runtime.

## Worker и repair: выбор same против fresh

| Ситуация | Маршрут | Основание |
|---|---|---|
| Один конкретный пропуск реализации; contract однозначен; context свеж | **PROPOSAL:** follow-up тому же worker | Локальная память снижает повторное чтение; независимость обеспечивает reviewer. |
| Worker вернул обоснованный `BLOCKED` из-за интерфейса/zone | **PROPOSAL:** contract repair orchestrator/researcher, затем worker с amended packet | **OBSERVED:** несколько V1 BLOCKED до кода были настоящими defects контракта. |
| Повторяется тот же defect class после одной содержательной попытки | **PROPOSAL:** fresh repair context; при высокой сложности также stronger class | **OBSERVED:** повторное направление Terra по той же схеме не помогало T07; fresh Sol помог. |
| Изменились acceptance criteria или write zones | **PROPOSAL:** новый ticket/packet, не follow-up | Старый context содержит уже неверный контракт. |
| Reviewer disagreement | **PROPOSAL:** evidence adjudication/research, не majority vote | **OBSERVED:** disagreement в T10 выявил contract gap. |
| Environment/permission failure | **PROPOSAL:** preflight/authority resolution, не смена модели | Сильнее reasoning не выдаёт отсутствующее право или tool. |

## Reviewer topology

- **OBSERVED:** upstream предписывает два persistent reviewers; V1 в финале использовал три независимых axis reviewers и три targeted re-reviewers.
- **INFERENCE:** ценность создаёт независимость мандатов, а не фиксированное число или вечный thread.
- **PROPOSAL:** low-risk ticket — один reviewer с combined correctness/spec mandate; high-risk seam — параллельные независимые axes; final whole-repo review — минимум один fresh verifier плюс риск-обусловленные axes.
- **PROPOSAL:** reviewer получает diff/base, requirements/contract и verification commands, но не самооценку worker до первичного verdict.
- **OPEN:** может ли native `/review` всегда использоваться вместо reviewer subagent для всех scopes/surfaces; нужен runtime experiment.

## Researcher: когда действительно нужен

- **PROPOSAL:** вызывать только при явной unknown, способной изменить contract/routing: external API semantics, repo architecture, reproducible behavior, official capability.
- **PROPOSAL:** codebase exploration и official-doc research разделять, чтобы authority источников не смешивалась.
- **FACT:** для technical external facts authoritative source должен быть официальным/primary; API model page не доказывает доступность модели в Codex surface.
- **PROPOSAL:** researcher завершает задачу verdict `CONFIRMED / CONTRADICTED / UNRESOLVED` и указывает impact; он не расширяет feature scope.

## Нужны ли дополнительные постоянные роли

| Кандидат | Решение V1 | Обоснование |
|---|---|---|
| Planner | **PROPOSAL: не отдельная постоянная роль** | Planning — фаза orchestrator; независимый plan review можно дать fresh reviewer/researcher. |
| Integrator | **PROPOSAL: не отдельный agent type** | Orchestrator выполняет механическое integration; содержательный conflict превращается в repair ticket владельцу зоны. |
| Security reviewer | **PROPOSAL: риск-мандат reviewer, не always-on role** | Нужен для auth/secrets/network/data/destructive surfaces; не нужен для каждого текстового change. |
| UX/craft reviewer | **PROPOSAL: риск-мандат reviewer** | Нужен, когда acceptance зависит от interface/visual interaction; comparable и live run обязательны. |
| Memory agent | **PROPOSAL: не постоянный** | Durable checkpoint строится из verified run ledger; project documentation — отдельный opt-in worker. |
| Dashboard agent | **DROP / PROPOSAL** | UI состояния не требует agent identity и не входит в correctness core. |

## Контекстная долговечность

```text
логически весь run:   orchestrator role + durable ledger
на один ticket:       worker thread
на один вопрос:       researcher thread
на один verdict axis: reviewer thread
на один defect:       repair thread (same или fresh по cause)
на acceptance:        fresh blind verifier
```

- **FACT:** официальная документация не обещает точную fresh-context semantics или lifetime subagent threads.
- **OBSERVED:** V1 handles потерялись между сессиями/compaction.
- **PROPOSAL:** любой role/thread должен быть заменим после checkpoint; восстановление не может зависеть от возможности «resume этого агента».

## Минимальный протокол взаимодействия

1. **PROPOSAL:** orchestrator фиксирует packet ID, contract version, dependencies, write zones и done evidence.
2. **PROPOSAL:** worker отвечает `DONE / BLOCKED / FAILED` по schema из [04-context-contracts.md](04-context-contracts.md).
3. **PROPOSAL:** orchestrator независимо проверяет actual changed paths и обязательные commands.
4. **PROPOSAL:** reviewer возвращает findings с evidence и owner/cause hypothesis; не пишет.
5. **PROPOSAL:** orchestrator adjudicates contract vs implementation и создаёт repair packet.
6. **PROPOSAL:** acceptance verifier получает только current brief + runnable repo + constraints.
7. **PROPOSAL:** после каждого material transition durable checkpoint делает смену thread безопасной.

## Незакрыто

- **OPEN:** какой минимум независимых review axes нужен по risk class.
- **OPEN:** можно ли технически гарантировать read-only reviewer во всех поддерживаемых surfaces при parent live overrides.
- **OPEN:** какое effective context получает native spawned agent и как доказать fresh-context требование.
- **OPEN:** нужен ли отдельный integration worker после эксперимента с concurrent worktrees.
