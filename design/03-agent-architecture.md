# Agent architecture

**DECISION.** Три логические роли достаточны: orchestrator, worker, reviewer. Built-in agent type — выбираемый runtime resource, не роль/permission guarantee. Эта карта заменяет proposed шесть ролей из [audit 02](../research/02-agent-roles.md), сохраняя их полезные мандаты.

## Responsibility and permissions

| Role | Responsibility / lifetime | Input → output | Read / write / ownership |
|---|---|---|---|
| Orchestrator | Логический owner всего run; session заменима на checkpoint | User intent + ledger + evidence → versioned plan/packets, decisions, integration receipts, final report | Читает project по authority; единственный writer canonical state/docs/evidence; ledger через helper; владеет mechanical Git actions по 06; product edits выполняет worker |
| Worker | Один ticket/attempt; bounded goal и zone | Worker packet → structured local result | Читает scoped project/contract pointers; пишет только lease zone + declared disposable test scratch и exact return inbox по 05; не владеет Git metadata и ledger |
| Reviewer | Один independent mandate/subject revision; disposable thread | Review/research/acceptance packet → evidence and verdict | Логически read-only к product и ledger; результаты через qualified file/message transport. Test-generated data допустимы только в disposable scratch по 06 |

Orchestrator не выдаёт worker authority сверх user scope/sandbox. Worker не меняет contract/criteria/zone и не dispatch других агентов. Reviewer не реализует свои findings и не принимает собственные fixes. Setup одного optional reviewer agent возможен только при exact authority и E03 qualification; скрытая установка configs/instructions не часть run.

## Orchestrator context contract

Всегда в active working context: run ID/phase, current next_action, relevant gate, current risk/blockers и IDs рабочих задач. Full ledger хранится в файле; helper выдаёт необходимый slice, а не каждую историческую revision. Новое решение сохраняется до следующего dispatch. После compaction/resume обязательный re-grounding по 08; summary не заменяет phase rules.

Orchestrator делает небольшие read-only inspections сам, когда передача вопроса увеличит работу. Самостоятельный product fix не является такой оптимизацией. Контекстная ёмкость и capability назначения моделей — [04](04-routing-and-escalation.md), [07](07-preflight-capabilities.md).

Persistent identity нужна только логическому owner token/epoch для coordination. Agent handle, parent conversation, model и UI-thread не durable dependencies. Fresh orchestrator восстанавливается по [02](02-run-ledger-and-artifacts.md), затем получает новую owner epoch.

## Worker and repair

Новый worker thread создаётся на новый ticket, изменённый contract/zone, lost worker и context retry. Fresh packet-only context предпочтителен; eligibility и допустимый DEGRADED_CONTEXT определены ниже. Он начинает с проверки packet identity, actual checkout/base, instructions и исполнимости criteria. Завершение — return по [05](05-task-and-return-contracts.md); DONE ещё не закрывает ticket.

Repair — тот же role с `mode=repair`, accepted finding refs и regression obligation. Same live worker допустим при локальном однозначном пропуске и неизменном packet contract; новая attempt identity обязательна. Fresh required при изменении intent/contract, повторе того же causal defect, anchoring или потере thread. Один и тот же agent никогда не получает следующий несвязанный ticket ради «экономии разогрева».

Worker имеет persistent identity только на время исполнения и допустимого local follow-up. Перед передачей контекста сохраняются completed/remaining и relevant failed hypotheses; raw history не передаётся.

## Reviewer mandates

| Mandate | Что проверяет | Fresh/read policy | Criterion завершения |
|---|---|---|---|
| `coverage` | Current user intent → proposed spec/contracts; omissions, silent narrowing | Fresh к authored design; видит intent и design, не narrative его защиты | Все active requirements assessed, findings с expected/actual; PASS только без blocking gap |
| `plan` | DAG, write ownership, contract producers/consumers, oracle feasibility | Fresh; только relevant plan+contracts+repo facts | Executable coverage и ownership проверены для каждого planned slice |
| `change` | Candidate diff/product по contract; correctness/craft и risk axes | Fresh initial review; self-report исключён | Tested scope, evidence и verdict на exact candidate |
| `research` | Один вопрос, который меняет decision/contract | Fresh на вопрос; read-only code/docs/reproduction | CONFIRMED/CONTRADICTED/UNRESOLVED с primary evidence и impact |
| `acceptance` | Observable product против current authorized intent | Всегда fresh, отдельная clean projection; [05](05-task-and-return-contracts.md) | Outcome каждого active criterion, runnable evidence; не читает implementation history |

**DECISION:** researcher не отдельный agent type/постоянный процесс. Мандат `research` назначается reviewer-role с подходящим built-in explorer/default. Он возвращает факты и uncertainties, не принимает scope за пользователя. Вызывается только при конкретной unknown, не перед каждым ticket.

Review continuity хранится в immutable review returns и typed issues ledger. Targeted re-review может получить finding IDs и новое candidate evidence; final acceptance каждый раз начинает с clean packet без предыдущих verdicts/repair narrative. Reviewers разных осей получают разные вопросы и возвращают verdicts независимо.

## Isolation and context eligibility

**FACT:** native subagents могут наследовать sandbox; custom defaults могут быть перекрыты live parent settings. Built-in explorer не read-only guarantee. [Official Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents).

Context freshness, author independence и authoritative write integrity — разные capabilities. Новый handle не доказывает ни одной. E02 квалифицирует context, E03 — review transport/isolation, 06 задаёт integrity barrier.

| Mandate | Sufficient evidence / fallback |
|---|---|
| Worker, repair, research | Новый bounded packet/thread; behavioural marker test с positive control определяет observed context. Inherited/unknown history → DEGRADED_CONTEXT с записанным anchoring/cost risk, execution допустим при leases/audit/independent review. Новый thread с тем же contaminated history не называется доказанно fresh |
| Coverage, plan, change review | Separate author-independent initial context. E02 behavioural clean test с positive control достаточен как operational qualification, без заявления strict isolation proof. Known inherited author/worker narrative делает route ineligible; нужен другой qualified context. Targeted re-review может читать свои findings |
| G5 final verifier | Automatic: strict input/runtime evidence + smoke; native non-recall недостаточен. V1 fallback: user-assisted independent clean session по 05/06, с explicit setup evidence и `MANUAL_ATTESTED_CLEAN`, не `STRICT_FRESH` runtime claim. Current-intent projection и запрет inherited implementation narrative сохраняются |

Degraded worker context не ослабляет blind G5 и не превращает parent в implementer. Нет native workers → planning/status/recovery и explicit execution blocker. По результатам E03 automatic routine review qualified в detection mode, automatic strict critical/G5 не qualified. V1 использует planned user-assisted fallback для G5 и required critical axes (05/06); это явная граница автоматизации, не отказ от review. Ручной routine review-only workflow не является V1 baseline. Без admissible independent result соответствующий gate остаётся BLOCKED.

Reviewer invariant: он не может незаметно изменить authoritative candidate/run state. Disposable mutation tests допустимы; сам reviewer не поставляет accepted repair. Routine mechanism выбран по [E03 evidence](../experiments/E03-reviewer-isolation-and-transports.md). Для manual critical/G5 техническая граница среды и evidence grade определены в 06; read-only label или ручной запуск сами по себе не qualification.

## Who repairs after review

1. Reviewer возвращает finding. Orchestrator проверяет reference/version и adjudicates cause, сохраняя исходный verdict.
2. Contract defect → orchestrator version-publishes canonical contract Markdown и refs по authority, G2/G3 affected validation. Product repair — отдельный packet.
3. Implementation defect → worker/repair в минимальной зоне, regression proof. Reviewer context не переиспользуется как worker.
4. Semantic integration conflict → worker с отдельной integration-repair зоной. Orchestrator выполняет лишь механическое применение проверенного результата.
5. Новый reviewer/re-review проверяет candidate. Для final acceptance используется новый clean verifier round.

## Shared resources and delegation bounds

Только orchestrator spawn/steer/stop; nested delegation в V1 выключена policy. Serial product writer — [06](06-safety-write-git-model.md). Независимые read-only задачи допускают concurrency, ограниченную фактически доступными slots и frozen snapshots; reviewers не читают движущийся target.

Canonical `.autopilot` state/docs/objects/packets orchestrator-owned. Единственное child metadata grant — exact attempt inbox в scratch по 05; оно не разрешает обновлять status/ledger/packet. Заявления agents становятся evidence после validation orchestrator. Role permission — contractual least privilege, не обещание OS enforcement semantic zones.

**Completion:** любой роль/мандат можно recreate из ledger projection; каждой записи/изменению есть owner; self-review и reviewer repair отсутствуют; постоянного researcher/planner/integrator не требуется.
