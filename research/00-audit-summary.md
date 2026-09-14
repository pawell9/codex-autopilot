# Autopilot audit summary

Дата среза: 2026-09-12. Это audit/design input, а не спецификация и не реализация нового skill.

## Метки утверждений

- **FACT** — явно подтверждено проектным источником или актуальной официальной документацией.
- **OBSERVED** — зафиксировано в первичных артефактах Idea Scout V1.
- **INFERENCE** — вывод из нескольких фактов/наблюдений; требует проверки дизайном или экспериментом.
- **PROPOSAL** — рекомендуемое направление для следующего design-pass; сейчас не реализуется.
- **OPEN** — решение намеренно не закрыто имеющимся evidence.

## Роли источников

- **FACT:** [PROJECT-BRIEF.md](../PROJECT-BRIEF.md) и [handoff](../references/handoffs/codex-autopilot-handoff.md) задают намерение и ограничения проекта, но не доказывают возможности Codex.
- **FACT:** технической истиной о текущем Codex считаются только [официальный индекс и snapshots](../references/official/openai-links.md) и связанные страницы OpenAI.
- **OBSERVED:** [Idea Scout V1](../references/idea-scout-v1/) — evidence одного принятого T3-run, а не универсальный benchmark.
- **FACT:** [использованный skill](../references/idea-scout-v1/autopilot-skill-used/) и [upstream baseline](../upstream/autopilot/) имеют одинаковое содержимое по рекурсивному `diff`; текущий corpus не показывает эволюцию между ними.
- **INFERENCE:** [community/video/workspace](../references/community/) полезны как каталог гипотез, но их неподтверждённые лимиты и config-синтаксис нельзя переносить в V1.

## Сравнение четырёх обязательных слоёв

| Аспект | Used Autopilot | Current upstream | Idea Scout V1 reality | Current official Codex | Вывод |
|---|---|---|---|---|---|
| Версия | **FACT:** 21-файловая копия baseline. | **FACT:** то же содержимое; recursive diff пуст. | **OBSERVED:** отклонения появились во время исполнения, не из-за version drift. | Не применимо. | **INFERENCE:** audit должен менять assumptions/mechanics, а не «догонять upstream». |
| Оркестрация | Fresh subagent/ticket, persistent reviewer handles, cap parallel writers. | То же. | **OBSERVED:** hybrid Claude→Codex sessions; explicit worktrees; reviewers пересоздавались; repair caps превышались. | **FACT:** native subagents, summaries, per-spawn routing, `/review`, worktrees. | **PROPOSAL:** заменить bridge/handles native primitives, сохранив role contracts и checkpoints. |
| Контекст | Paths вместо raw content; 50-tool-call handoff proxy. | То же. | **OBSERVED:** boundary rules приходилось копировать; file handoff пережил stop. | **FACT:** AGENTS chain, progressive skill disclosure, child summaries; exact fresh-context schema не задана. | **PROPOSAL:** packet+version+structured return; никаких tool-call constants. |
| Проверка | Per-ticket Manifest/Spec/Craft review и финальная blind acceptance. | То же. | **OBSERVED:** live/edge/mutation и 3+3 final reviewers нашли дефекты после green suites. | **FACT:** native read-only review и multi-axis subagent patterns поддержаны. | **PROPOSAL:** сохранить независимость, добавить oracle plan, topology выбирать по risk. |
| Safety/state | `.autopilot` ownership, zones, one-ticket commit, JS dashboard state. | То же. | **OBSERVED:** zones/contracts менялись; git checkpoints спасли resume; dashboard necessity не доказана. | **FACT:** sandbox/approvals/worktrees защищают runtime boundaries, но не semantic zones. | **PROPOSAL:** durable ledger+write-set validation; UI optional; technical и instruction guarantees разделить. |

## Главные выводы

1. **OBSERVED:** главная ценность Autopilot — не Claude-способ запуска агентов, а lifecycle: traceability от brief до acceptance, независимые проверки, маленькие rollback-точки, явные контракты и восстановление из файлов+git.
2. **OBSERVED:** «зелёные тесты + правдивый отчёт исполнителя» недостаточны. В T07 набор пропускал около 97% данных, а дефект нашли живой прогон и прямые проверки; финальный repository review после формального завершения нашёл ещё 19 root defects ([review log](../references/idea-scout-v1/run-artifacts/2026-09-05-idea-scout/review-log.md)).
3. **OBSERVED:** значительная часть repair была вызвана не слабостью исполнителя, а дефектами или неоднозначностью контракта. До первой строки кода workers несколько раз корректно вернули `BLOCKED`; расхождение двух reviewers также обнаружило contract gap.
4. **OBSERVED:** фиксированные потолки «два repair» и «два handoff» не описывают реальный T3-run: итоговое состояние содержит 37 repair и 7 handoff на 17 тикетов, включая 4–5 repair у отдельных тикетов и 6 handoff у T17 ([state.js](../references/idea-scout-v1/runtime-state/state.js)). Потолок полезен как триггер диагностики/escalation, но опасен как автоматический stop/fail.
5. **OBSERVED:** file/git checkpoints пережили аварийную остановку; agent handles и «постоянные» reviewers — нет. Resume был восстановлен по артефактам и checkpoint commits, а reviewer-потоки пришлось создать заново ([wave-4 pause handoff](../references/idea-scout-v1/run-artifacts/2026-09-05-idea-scout/handoff-2026-09-07-wave4-pause.md)).
6. **FACT:** современный Codex уже предоставляет subagents, модель/reasoning routing при spawn, summaries дочерних задач, `/review`, worktrees, goals, resume/compact, sandbox/approvals и structured output для `codex exec` ([Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents), [Code review](https://learn.chatgpt.com/docs/code-review), [Long-running work](https://learn.chatgpt.com/docs/long-running-work), [Non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode)).
7. **INFERENCE:** Codex-native версия может убрать Claude↔Codex bridge, копирование общих правил в каждый prompt и самодельное управление agent processes. Она не может убрать методические gates, explicit ownership, durable state и независимую проверку результата.
8. **FACT:** sandbox защищает общие границы, а не смысловую ownership-модель Autopilot. В `workspace-write` `.git`, `.agents` и `.codex` защищены рекурсивно, но `.autopilot/**` и обычные project files не получают семантическую защиту зон автоматически ([Agent approvals & security](https://learn.chatgpt.com/docs/agent-approvals-security)).
9. **OPEN:** официальные страницы расходятся в словаре reasoning effort, model slug и трактовке `Ultra`; доступность моделей зависит от поверхности, плана и rollout. Routing нельзя хардкодить без runtime preflight ([официальный реестр противоречий](../references/official/openai-links.md#выявленные-расхождения-в-официальных-источниках-для-проверки-в-runtime)).

## Что доказало ценность

| Элемент | Вердикт | Основание |
|---|---|---|
| Brief → manifest → spec → tickets → acceptance traceability | **KEEP / OBSERVED** | Две G2-проверки нашли 18 omissions/drift, 16 были исправлены; вторая поймала регрессию после переписывания спеки. |
| Blind review без внутренних артефактов | **KEEP / OBSERVED** | Проверяющий оценивал реализованное по brief и живому продукту, а не правдоподобность плана. |
| Вертикальные тикеты, dependencies, write zones, shared interfaces | **KEEP+MODIFY / OBSERVED** | Дали единицу исполнения и rollback; при этом зоны и контракты пришлось многократно уточнять. |
| Independent review и отдельный repair | **KEEP / OBSERVED** | Разные мандаты находили разные классы дефектов; repair тем же reviewer запрещал самоодобрение. |
| Живые/edge/mutation проверки | **ADD TO CORE / OBSERVED** | Именно они обнаружили data loss, фиктивные guards и тесты, закрепившие ошибочное поведение. |
| Один тикет — один checkpoint/commit | **KEEP+MODIFY / OBSERVED** | Позволил восстановить незавершённую волну и локализовать исправления; merge/worktree mechanics требуют Codex-native политики. |
| Durable run artifacts | **KEEP / OBSERVED** | Resume состоялся без прежней chat history и без сохранённых handles. |
| Честный final report, placeholders/deferred/dropped | **KEEP / INFERENCE** | Поддерживает продуктовую traceability; реализация представления может быть проще. |

## Legacy Claude-oriented architecture

- **FACT:** upstream предполагает orchestrator, который вручную отправляет отдельного subagent на тикет, хранит handles reviewers, копирует executor/craft contracts и обслуживает собственный dashboard/state protocol.
- **OBSERVED:** Idea Scout использовал гибридный Claude orchestrator → Codex executors и был вынужден дословно вкладывать boundaries в каждый Codex prompt, потому что bridge того прогона не передавал проектные инструкции автоматически ([executor rules](../references/idea-scout-v1/agent-rules/docs/executor.md)).
- **OBSERVED:** запрошенная agent-managed worktree isolation была очищена до завершения background Codex; пришлось перейти на явно созданные orchestrator worktrees.
- **INFERENCE:** переносить CLI bridge, ephemeral handles и Claude tool-call ceiling как архитектурные константы в Codex-native skill не следует.
- **PROPOSAL:** сохранить намерение этих механизмов — isolation, bounded context, independent verification, resumability — и заменить конкретную механику официальными Codex primitives только после capability preflight.

## Что Codex-native позволяет упростить

- **FACT:** subagents возвращают main thread summary и могут получать явные model/reasoning overrides; built-in `worker` и `explorer` уже существуют.
- **FACT:** `/review` запускает отдельного reviewer без изменения working tree; worktrees и goal/resume являются штатными возможностями.
- **INFERENCE:** в V1 не нужны собственный process bridge, hardcoded agent handles, custom TOML roles или обязательный HTML dashboard.
- **PROPOSAL:** оставить один компактный durable run ledger и task packets; native thread UI использовать как live visibility, но не как единственное состояние.
- **PROPOSAL:** reviews разделять по независимым мандатам только по риску, а не всегда держать два постоянных процесса.

## Главные риски

| Риск | Тип | Ответ для V1 |
|---|---|---|
| Контракт неверен, worker формально прав | **OBSERVED** | `BLOCKED` не штраф; классифицировать cause и вернуть контракт orchestrator/researcher. |
| Тесты кодифицируют неверное поведение | **OBSERVED** | Добавить live/edge/oracle check для критичных seams. |
| Parallel writes конфликтуют или ломают ownership | **FACT+OBSERVED** | Read-heavy parallel by default; write tasks — disjoint zones либо отдельные explicit worktrees. |
| Reviewer логически read-only, но runtime override даёт write | **FACT** | Проверять sandbox; instruction-only запрет считать defense-in-depth, не гарантией. |
| Model/effort недоступны или имена изменились | **FACT** | Capability discovery + fallback classes, без безусловных model IDs. |
| Run зависит от чата/handle | **OBSERVED** | Checkpoint state + git evidence; agent lifetime не считать durable. |
| Методика разрастается быстрее полезной работы | **INFERENCE** | Надёжное ядро V1, optional UI/polish/ADR/advanced automation вне critical path. |

## Готовность к следующему этапу

- **FACT:** corpus достаточен, чтобы определить lifecycle, роли, контекстные и write-контракты, preflight и границы V1.
- **OPEN:** до реализации остаются решения о формате durable ledger, минимальной git-стратегии, runtime discovery моделей/effort и критерии включения external/Astra review.
- **PROPOSAL:** следующий отдельный architecture/design pass должен превратить документы `01–08` в одну согласованную state machine и testable contracts. Этот аудит этого не делает.

Итог: **готово к отдельному architecture/design pass при сохранении перечисленных OPEN как явных решений, а не скрытых допущений.**
