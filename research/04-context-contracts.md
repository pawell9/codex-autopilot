# Context contracts

Цель — определить минимальный воспроизводимый task packet и return/checkpoint contract. Это design input; prompt и schema implementation здесь не создаются.

## Метки

`FACT` — подтверждено; `OBSERVED` — evidence V1; `INFERENCE` — синтез; `PROPOSAL` — проектное направление; `OPEN` — не закрыто.

Empirical anchors: [review log](../references/idea-scout-v1/run-artifacts/2026-09-05-idea-scout/review-log.md), [executor contract фактического run](../references/idea-scout-v1/agent-rules/docs/executor.md), [tickets](../references/idea-scout-v1/run-artifacts/2026-09-05-idea-scout/tickets/) и [pause handoff](../references/idea-scout-v1/run-artifacts/2026-09-05-idea-scout/handoff-2026-09-07-wave4-pause.md).

## Evidence, из которого следует контракт

- **OBSERVED:** workers Idea Scout несколько раз нашли contract defects ещё до кода; это полезный результат, а не failure исполнения.
- **OBSERVED:** T07 показал, что корректный worker summary и зелёные тесты не заменяют независимый oracle/live check.
- **OBSERVED:** копирование полного boundary block в каждый Codex prompt было workaround гибридного bridge, а не доказанной универсальной необходимостью.
- **FACT:** Codex subagents возвращают summaries и предназначены в том числе для разгрузки main context, но machine-readable schema их summary официально не зафиксирована ([Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)).
- **FACT:** `codex exec --output-schema` может валидировать final JSON non-interactive run, но это не документированный встроенный межагентный protocol ([Non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode)).
- **INFERENCE:** task contract должен быть skill-owned и проверяемым независимо от transport: native subagent, `codex exec` или будущий adapter.

## Task packet исполнителю

### Обязательный envelope

| Поле | Смысл | Почему обязательно |
|---|---|---|
| `packet_id` | Стабильный ID попытки | Связывает return, review, repair и checkpoint. |
| `ticket_id` | Стабильная единица результата | Не смешивает несколько целей в одном context. |
| `contract_version` | Версия acceptance/interfaces/zones | **OBSERVED:** amendments меняли допустимый путь реализации. |
| `goal` | Один observable outcome | Не список внутренних действий. |
| `done_when[]` | Проверяемые условия | Отделяет «код написан» от результата. |
| `requirement_refs[]` | ID + короткая исходная формулировка | Сохраняет traceability и wording пользователя. |
| `read_scope[]` | Начальные пути/источники | Снижает разведку без запрета читать необходимую зависимость. |
| `write_allow[]` | Точные файлы/каталоги/patterns | Основа semantic ownership. |
| `write_deny[]` | Shared/protected/out-of-scope paths | Делает запреты явными, даже если sandbox шире. |
| `interfaces_in[]` | Потребляемые signatures/schemas/invariants | Минимизирует чтение orchestration history. |
| `interfaces_out[]` | Что ticket обязан создать/сохранить | Позволяет следующим tickets работать по contract. |
| `dependencies[]` | Завершённые prerequisites + evidence refs | Worker не должен угадывать readiness. |
| `verification_plan` | Commands/scenarios/oracles и expected evidence | Предотвращает «зелёный не тот test». |
| `environment_facts` | Проверенные tool/version/constraints, без secrets | Убирает повторный preflight и ложные предположения. |
| `stop_conditions[]` | Когда вернуть `BLOCKED`, а не импровизировать | Защищает scope/interfaces/data. |
| `return_contract` | Ожидаемые status/fields/лимит | Делает ответ валидируемым и компактным. |

### Контекст по необходимости

- **PROPOSAL:** relevant code paths или стартовые symbols, но не pasted repository.
- **PROPOSAL:** минимальные excerpts current brief/spec только для требований ticket; канонические artifacts передавать ссылками/путями.
- **PROPOSAL:** findings конкретного repair с evidence и expected proof, но не полный журнал спора.
- **PROPOSAL:** known failed attempts как короткие `attempt / result / why-not-repeat`; только если они меняют выбор следующего подхода.
- **PROPOSAL:** risk flags (`data-loss`, `auth`, `migration`, `external-side-effect`, `cross-platform`, `visual`) для routing и verification depth.

## Что нельзя передавать worker по умолчанию

| Не передавать | Причина |
|---|---|
| Полную orchestration/chat history | **FACT+INFERENCE:** загрязняет context; official subagent guidance рекомендует возвращать summaries. |
| Полные raw logs/diffs предыдущих агентов | Нужны evidence pointers и relevant excerpt, а не шум. |
| Secret values, `.env` contents, credentials | **FACT:** least privilege; upstream redaction contract и project brief запрещают утечки. |
| Нерелевантные tickets/spec sections | Расширяют perceived scope и создают accidental coupling. |
| Внутренний final verdict предыдущего reviewer до независимого review | Anchoring и потеря независимости. |
| Неподтверждённые community/model claims как capabilities | Community — только hypothesis; capability идёт из preflight/official docs. |
| Разрешение «правь всё необходимое» | Разрушает write ownership; отсутствие нужной зоны → `BLOCKED`. |
| Старый contract без version/hash | **OBSERVED:** V1 amendments делали старые assumptions опасными. |

## Structured return contract

### Общий envelope

| Поле | Contract |
|---|---|
| `packet_id`, `ticket_id`, `contract_version_seen` | Должны точно совпасть с packet. |
| `status` | Только `DONE`, `BLOCKED`, `FAILED`, `HANDOFF`. |
| `summary` | Краткий observable result, не self-rating. |
| `changed_paths[]` | Каждый созданный/изменённый/удалённый path; проверяется независимо. |
| `verification[]` | `command_or_scenario`, `result`, `exit/evidence_ref`, `scope`; запрещено просто «tests pass». |
| `requirements[]` | `requirement_id → evidence/status`. |
| `interface_changes[]` | `none` либо exact before/after и требуемый amendment. |
| `risks_or_unknowns[]` | Только остающиеся и material. |
| `next_action` | `review`, `contract_repair`, `environment_action`, `retry`, `none`. |

### DONE

- **PROPOSAL:** разрешён только при выполненных `done_when`, declared write set и successful required verification.
- **PROPOSAL:** worker не утверждает окончательный acceptance; он заявляет локальную completion, затем идут independent checks.
- **PROPOSAL:** отсутствие изменений допустимо только если outcome уже существовал и это доказано; orchestrator решает, закрывать ли ticket.

### BLOCKED

Обязательные поля: `blocker_type`, `evidence`, `required_decision_or_change`, `safe_partial_state`, `changed_paths`.

`blocker_type` — **PROPOSAL:**

- `CONTRACT_MISSING_OR_CONTRADICTORY`
- `WRITE_ZONE_MISSING_OR_OVERLAP`
- `DEPENDENCY_NOT_READY`
- `PERMISSION_OR_SANDBOX`
- `TOOL_OR_ENVIRONMENT`
- `USER_AUTHORITY_REQUIRED`
- `EXTERNAL_STATE`
- `UNKNOWN`

**OBSERVED:** ранний `BLOCKED` часто был самым дешёвым способом найти ошибку plan/interfaces. Его нельзя автоматически считать repair-count worker.

### FAILED и HANDOFF

- **PROPOSAL:** `FAILED` — подход выполнен, но verification доказала несовпадение; нужны failure evidence и классификация cause.
- **PROPOSAL:** `HANDOFF` — context/transport прекращается при сохранённом safe state; нужны completed/remaining, changed paths, exact commands/results, open assumptions и proposed next packet.
- **OPEN:** точный context saturation signal native Codex официально не стандартизован; нельзя использовать upstream «50 calls» как техническую истину.

## Review return contract

Каждая находка:

| Поле | Смысл |
|---|---|
| `finding_id` | Стабильный ID для repair/re-review. |
| `axis` | `requirement`, `correctness`, `security`, `data`, `ux`, `maintainability`, `verification`. |
| `severity` | Блокирующая для acceptance или advisory; без искусственной точности. |
| `claim` | Одно проверяемое несовпадение. |
| `evidence` | File:line, command/result, live step или authoritative source. |
| `expected` / `actual` | Контракт против наблюдения. |
| `cause_hypothesis` | `implementation`, `contract`, `environment`, `unknown`; явно hypothesis. |
| `owner_hint` | Orchestrator, worker, user или environment. |

- **PROPOSAL:** итог reviewer — `PASS`, `BLOCK`, `UNVERIFIABLE`, но PASS не отменяет blind acceptance.
- **PROPOSAL:** пустой результат должен перечислить реально проверенные scopes/commands.

## Checkpoint и handoff

### Когда checkpoint обязателен

- **PROPOSAL:** после утверждения/изменения brief или contract version;
- **PROPOSAL:** до dispatch wave и после каждого интегрированного ticket;
- **PROPOSAL:** перед compaction, сменой orchestrator thread или остановкой;
- **PROPOSAL:** перед destructive/migration step и после подтверждённого rollback point;
- **PROPOSAL:** после adjudication reviewer disagreement;
- **PROPOSAL:** перед final acceptance.

### Минимальное содержимое

- current goal/run ID and status;
- brief/requirements/contract version refs;
- integrated base commit or explicit no-git snapshot identity;
- tickets: ready/running/review/repair/done/blocked;
- active write ownership and worktree mapping;
- last verified commands/results;
- unresolved decisions/authority blockers;
- spawned agents только как optional observability, не dependency resume;
- exact next safe action.

- **OBSERVED:** V1 resume сработал благодаря files+checkpoint commits и точному handoff; handles reviewers не были durable.
- **PROPOSAL:** checkpoint считается достаточным, если fresh orchestrator может определить next safe action без старого chat.

## Fresh-context policy

- **PROPOSAL:** fresh worker на новый ticket; fresh verifier на blind acceptance; fresh reviewer для независимого первичного verdict; fresh researcher на отдельную unknown.
- **PROPOSAL:** same-context follow-up допустим только для bounded repair того же contract и только один раз до cause checkpoint; это policy candidate, не доказанный универсальный limit.
- **PROPOSAL:** при contract change всегда новый packet; thread может остаться тем же только если ему явно аннулируют старую версию и runtime experiment докажет отсутствие anchoring — до этого fresh предпочтительнее.
- **FACT:** official docs не специфицируют точный объём inherited conversation history native subagent. Fresh означает методическую изоляцию packet, а не пока что доказанный нулевой history.

## Как не тащить orchestration history

```text
brief wording ─┐
contract slice ├─> task packet ─> worker return ─> evidence ledger
interfaces ────┤                         │
preflight facts┘                         └─> independent review packet

chat/logs/old attempts ─X─> только короткие decision/evidence records
```

- **PROPOSAL:** canonical artifacts передаются path+version/hash, не копируются целиком.
- **PROPOSAL:** main thread хранит decisions и state transitions; exploration/raw tool output остаётся в child thread или evidence file.
- **PROPOSAL:** следующий worker получает только актуальный interface contract и predecessor evidence, а не весь predecessor transcript.
- **PROPOSAL:** reviewer ledger хранит cross-ticket patterns; recreated reviewer читает ledger, не старый chat.

## Validation points для следующего этапа

- **OPEN:** формат ledger и schema language (JSON/JSONL/YAML/Markdown+validator).
- **OPEN:** какой native subagent transport поддерживает schema validation без `codex exec` adapter.
- **OPEN:** как вычислять/проверять contract version и actual write set атомарно.
- **OPEN:** threshold для same-context repair → fresh context должен быть подтверждён runtime eval, а не скопирован из upstream.
