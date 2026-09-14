# Routing and escalation policy

**DECISION.** Routing выбирает необходимую capability, затем доступный resource. Здесь policy; конкретный model catalog, effort strings, availability и квоты — runtime facts в [07](07-preflight-capabilities.md). Ни состояние run, ни gate не зависит от имени модели.

Основание: [routing audit](../research/03-model-reasoning-routing.md) различает contract defects и model failures. **OBSERVED:** fresh stronger worker помог T07 после повторных repairs; это не доказывает лестницу Terra→Sol→Astra или фиксированное число попыток. [Official Models](https://learn.chatgpt.com/docs/models) рекомендует повышать effort по необходимости и предупреждает о latency/token cost; доступность проверяется на выбранной surface.

## Task assessment: complexity отдельно от consequence

| Complexity | Признаки | Required capability |
|---|---|---|
| `bounded` | Один известный pattern, стабильный контракт, локальный oracle, малая неопределённость | Reliable scoped tool use and implementation |
| `coupled` | Несколько взаимозависимых interfaces, debugging causality, compatibility/concurrency | Multi-step reasoning across boundaries, evidence synthesis |
| `ambiguous` | Требования/contract/oracle конфликтуют, неизвестна причинность или архитектурный выбор | Explicit uncertainty handling, contract synthesis/adjudication |

Risk tier: `routine` (локальный reversible change с ясным oracle), `elevated` (public interface/data correctness/multiple consumers/UX critical flow), `critical` (security/trust, data loss/migration, weak rollback, irreversible effect). Отдельные flags фиксируют причину; tier не арифметическая сумма. Высокий risk может быть у короткого diff. Неопределённая risk classification → elevated до уточнения, uncertainty о destructive effect → critical. Upgrade по unknown сохраняет resolving question и owner; после research/ответа и до G3/dispatch orchestrator пересматривает tier по evidence. Plan risk не ниже максимума tickets и собственных integration risks.

Capability classes: `routine` (extraction/simple inspection), `implementation` (bounded coding/tool use), `deep` (coupled reasoning/complex review), `frontier` (hard unresolved cross-system judgment). Это Autopilot task requirements, не утверждение о ранге любого model slug. Неизвестный model не получает класс по имени; binding требует current official positioning, observed runtime availability и release/run evidence.

Reasoning bands: `light`, `standard`, `deep`, `exceptional`. Они не передаются tool напрямую. Preflight resolver связывает band с поддерживаемым model-specific effort или inherited default и записывает выбранное соответствие. `Ultra` не трактуется как generic effort. Нет static enum всех моделей/усилий в policy. Classes и bands — независимые требования, не 4×4 обязательных bindings. Resolver хранит только реально используемые sparse routes; одинаковые effective bindings deduplicate. E05 может упростить неразличимые mappings по evidence.

## Default paths

| Task | Capability / reasoning | Review and completion guard |
|---|---|---|
| Deterministic validation, ready DAG, projection | Deterministic helper; no model call | Schema/semantic validation |
| Narrow fact extraction / bounded research | routine или implementation / light–standard | Source evidence; unresolved не превращается в fact |
| Routine implementation | implementation / standard | Required oracle + independent combined change reviewer |
| Coupled/elevated implementation | deep / deep | Seams/regression checks; specific risk mandate |
| Ambiguous intent/contract | deep / deep, read-only first | Resolve authority/contract before code |
| Routine reviewer | implementation / deep, либо deep если causal complexity | Fresh mandate, evidence not self-report |
| Critical review/final complex acceptance | deep / deep; frontier only by escalation | Independent axis и negative/live proof; stronger model не отменяет gates |
| Orchestrator | Current session с достаточной synthesis capability | Helper для bookkeeping; expensive analysis делегируется bounded mandate |
| Local repair | Class исходного adequate route / standard или deep по defect | Changed hypothesis + regression proof; fresh rules ниже |

`implementation/standard` — **CONSERVATIVE DEFAULT**, а не доказанный economic optimum. Tiny tasks могут использовать routine class только после доказанной исполнимости pattern. Недоступность preferred binding не означает немедленное увеличение расходов или уменьшение review.

## Resolution algorithm (перед каждой новой attempt)

1. Из goal/criteria/interfaces/risk/cause определить required capability и reasoning band. Проверить, что проблема вообще решается моделью.
2. Взять только valid capability facts: доступные explicit bindings, inherited current route, selected model efforts, context and permission capabilities. Применить higher-priority user/project restrictions на routing.
3. Выбрать наименее затратный **из известных adequate** routes. Если сравнительной стоимости нет, предпочесть validated default, не выдумывать цены. Не выбирать по API price как по Codex credits.
4. Если override не разрешён/не обнаружен — использовать adequate inherited route, actual model может быть UNKNOWN. Identity и adequacy — отдельные fields. Перенести parent adequacy можно только при evidence effective inheritance chain: нет изменяющего model/effort agent default/custom layer. Иначе bounded representative qualification/oracle evidence может подтвердить opaque route без slug. Для coupled/critical unknown adequacy — один конкретный qualification/decomposition step с новым evidence; если gap остаётся, BLOCKED с условием снятия, без бесконечного дробления. Requested override с unknown resolution нельзя считать успешным.
5. Native rejection model/effort → invalidate именно binding, зафиксировать error. Проверить, был ли spawn фактически создан. Если нет — выбрать valid fallback/inherit; если неизвестно — recovery, не duplicate spawn.
6. Persist route record, packet и prepared attempt до dispatch; observed resolution/handle приложить к следующему intent-level helper call; safety-critical rejection обрабатывается сразу. Нет отдельной обязательной route transaction. Запрошенное имя и фактически подтверждённая модель — разные поля.

Fallback graph: validated same-class route → inherited adequate route → smaller bounded decomposition с тем же outcome → BLOCKED capability. Frontier unavailable не блокирует V1 автоматически: deep + fresh independent axis + stronger oracle могут закрыть ту же uncertainty. Если evidence по-прежнему недостаточно, gate остаётся BLOCKED.

## Cause-first triage

| Cause | First action | Что не является remedy |
|---|---|---|
| `implementation` | Reproduce expected/actual; local repair или fresh causal investigation | Переписать criterion под существующий код |
| `contract` / `user_intent` | Orchestrator adjudication; bounded research при unknown; version amendment и affected gates | Stronger worker, которому молча разрешено придумать semantics |
| `oracle` | Независимо восстановить expected outcome из current intent; исправить verification contract | Больше запусков того же нерелевантного теста |
| `environment` / `permission` | Conditional preflight; local reproducible fix в отдельной authorized zone или user action | Повышение model/effort, обход denial другим tool |
| `ownership` | Quarantine actual write set; resolve zone/base/foreign changes | Silent allowlist expansion |
| `orchestration` | Ledger/packet/operation recovery; correct state/dispatch defect | Оценивать worker как плохую модель |
| `unknown` | Fresh read-only reproduction/diagnosis | Случайный repair или automatic escalation по счётчику |

Исходный worker BLOCKED на настоящем contract gap считается полезным finding, не model-quality failure. Counters отдельно: transient retries, implementation repairs, contract amendments, environment recoveries и handoffs.

## Retry, repair, fresh context, escalation

`Retry` повторяет безопасную операцию после подтверждённого transient cause, без изменения solution. Требует reconciliation эффектов и evidence изменившегося условия; repeated same failure без такого evidence → diagnostic checkpoint. Side effect с неизвестным результатом не повторяется.

`Repair` меняет solution по accepted finding. Для каждой attempt обязательны finding/cause, hypothesis, expected new proof и stopping condition. При неизменном contract и одном локальном пропуске same live worker может использовать прежний контекст; отдельный attempt record всё равно создаётся.

`Fresh-context retry/repair` обязателен после contract/intent/zone amendment, lost/context-saturated worker или повторения того же causal defect после substantive repair. Context содержит concise failed hypothesis только если без него повтор вероятен. При недоступной доказанной freshness новый bounded thread отмечается DEGRADED_CONTEXT по 03, а не бесконечно перезапускается. Это default против зацикливания, не empirically optimal numeric threshold.

`Stronger reasoning` оправдан, когда исходная задача требовала более глубокой причинности, чем выбранный effort. `Stronger model` оправдан при verified complexity mismatch, persistent causal error при адекватном contract, либо нерешённом cross-boundary synthesis. Не требуется механически пройти все effort bands перед сменой capability class. Выбор фиксирует, какую конкретную неопределённость должен снять новый ресурс.

`De-escalation` — только на новой bounded attempt, когда контракт стабилен и pattern доказан. Никакого downgrade во время работающего ticket. Risk/oracle/reviewer independence не уменьшаются из-за того, что implementation уже получила PASS. Failure после downgrade возвращает к последнему adequate route для данного task class; oscillation без нового evidence запрещена.

## Progress bound instead of magic repair cap

Перед каждым repeat orchestrator сравнивает failure signature, hypothesis, evidence и method с предыдущими attempts. Следующая attempt допустима, только если меняется причинно значимый input/approach/capability и указан ожидаемый различающий результат. Перефразирование prompt не считается прогрессом.

Повторный same-class defect → обязательный diagnostic checkpoint до новой записи product. Diagnostic выбирает одно: fresh hypothesis, contract/oracle correction, qualified stronger route или BLOCKED с precise missing condition. Если перечисленные доступные решения исчерпаны и нового evidence нет, run приостанавливается/блокируется; бесконечно «ещё раз попробуем» не является разрешённым next_action.

Числовые ceilings attempts/tokens/time задаются только явным user budget или eval-derived release policy с provenance. Их достижение вызывает checkpoint и решение о continuation; не автоматический ACCEPTED/FAILED. Если бюджет не задан, действует описанный no-repeat-without-progress guard, а не скрытый бесконечный лимит. Количественная оптимизация — E05 в [10](10-decisions-and-experiments.md).

## Independent reviewer routing

Routine product ticket: один fresh combined reviewer по current criteria/correctness/craft. Elevated: добавить предметный mandate на фактический риск; его можно объединить с combined review, если один reviewer полноценно покрывает его и oracle. Critical: отдельный независимый reviewer по security/data/trust axis плюс основной reviewer; это conservative defense-in-depth, а не benchmark-derived оптимальное число.

Independent означает separate initial context/mandate/evidence; разные модели не обязательны. Reviewers одного candidate работают параллельно только на frozen isolated views. `/review` допустим как change-review transport после qualification scope/return/context; автоматическим equivalent final acceptance он не считается.

Conflicting reviewers: deduplicate только одинаковые expected/actual claims; сохранить оба verdicts, проверить evidence. Contract ambiguity → amendment, factual disagreement → fresh targeted reproduction, preference outside intent → advisory. Majority vote и «самая сильная модель сказала PASS» не закрывают вопрос без evidence.

## Astra / frontier / external review

Astra — пример возможного runtime binding `frontier`, не gate name. Рассмотреть frontier, когда unresolved ambiguity/reviewer disagreement/repeated causal failure сочетаются с critical consequence или дорого обратимым architecture decision. Точный экономический threshold неизвестен: E06.

**DECISION:** frontier и external review никогда не обязательная dependency V1. Native frontier можно использовать при доступной capability и уже разрешённом cost scope; новый оплачиваемый service/повышение тарифа требует отдельной authority. External provider/Claude не входит в автоматический transport V1: только explicitly requested, sanitized review handoff и импорт structured evidence; решение gate остаётся orchestrator.

Отсутствие Astra → deep fresh reviewer + independent axis/stronger oracle. Отсутствие внешнего review → обычный V1 path. Наличие unresolved critical concern → BLOCKED даже после frontier verdict без достаточного доказательства. Число systems touched, retries или tickets само по себе не является числовым Astra trigger.

## Economics and observability

Ledger хранит available usage signals, route/cause, time, attempts, repair outcome и context packet size. Unknown tokens/credits остаются null. Fast/Ultra/parallelism не включаются ради ритуальной скорости. Parallel reads оправданы независимыми вопросами, не свободным количеством slots. Product writers V1 serial; bounded parallel per-ticket worktrees — post-V1 E10. Happy path bookkeeping target и измерение E09 — 02/10.

**Completion routing design:** любой task разрешается через capability policy; unavailable names/efforts имеют ограниченный fallback; каждый failure cause имеет первый адресат; no-progress повтор останавливается; accepted criteria и safety не ослабляются при quota/model fallback.
