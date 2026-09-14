# Model and reasoning routing policy — design basis

Это policy proposal для следующего design-pass, не config и не обещание доступности моделей.

## Метки и граница источников

- **FACT** — подтверждено актуальной официальной документацией OpenAI/Codex.
- **OBSERVED** — поведение Idea Scout V1.
- **INFERENCE** — вывод из facts/observations.
- **PROPOSAL** — рекомендуемая routing policy, которую ещё нужно проверить.
- **OPEN** — противоречие или недостаток evidence; не закрывается догадкой.

**FACT:** страницы API используются только для capability/pricing API-моделей. Они не доказывают доступность модели в конкретной Codex surface/account. Основные источники: [Codex Models](https://learn.chatgpt.com/docs/models), [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents), [Configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference), [Code review](https://learn.chatgpt.com/docs/code-review) и локальный [реестр официальных источников](../references/official/openai-links.md).

**OBSERVED:** empirical routing evidence берётся из [Idea Scout review log](../references/idea-scout-v1/run-artifacts/2026-09-05-idea-scout/review-log.md) и [final state](../references/idea-scout-v1/runtime-state/state.js); это один T3-run, а не сравнительный model benchmark.

## Что подтверждено о текущей линейке

| Capability class | Официальное позиционирование | Подходящие классы задач | Ограничение интерпретации |
|---|---|---|---|
| `gpt-5.6-luna` | **FACT:** ясные, повторяемые, high-volume задачи с известным критерием результата. | Extraction, classification, deterministic transformations, structured summaries, узкие inspections. | **FACT:** low cost в API не равен точному Codex credit cost. |
| `gpt-5.6-terra` | **FACT:** pragmatic all-rounder для повседневной работы, strong reasoning/tool use без глубины Sol. | Scoped implementation, обычные tests/fixes, bounded code exploration. | **PROPOSAL:** default worker class, только если доступна и задача хорошо задана. |
| `gpt-5.6-sol` / `gpt-5.6` | **FACT:** сложная, открытая, high-value работа, требующая analysis, judgment или polish; API docs называют unsuffixed ID alias Sol. | Неоднозначные integration changes, сложный debugging, contract/architecture repair, high-risk review. | **OPEN:** alias против pinned slug и surface availability проверяются preflight. |
| `gpt-6-astra` | **FACT:** hardest end-to-end work across code/apps/research с длительным reasoning и judgment. | Системная cross-domain архитектура, особо сложная synthesis/adjudication, high-stakes whole-system review. | **FACT:** не доступна во всех plans/surfaces; docs не делают её обязательным reviewer. |

API model pages: [Astra](https://developers.openai.com/api/docs/models/gpt-6-astra), [Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol), [Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra), [Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna).

- **FACT:** OpenAI советует использовать минимальный reasoning effort, который даёт нужный результат; `Low/Light` — для scoped quick work, `Medium` — balance, `High/Extra High` — multi-step, sources, trade-offs, reviews/security edge cases.
- **FACT:** `Max` даёт больше reasoning одной задаче; `Ultra` на странице Models описан как режим с subagents. Большинству задач не нужны Max/Ultra.
- **FACT:** higher effort повышает latency/token use и не является документированной монотонной гарантией качества.
- **FACT:** subagent resolution: explicit spawn override → `[agents]` default → parent value; custom-agent config может перекрыть их. Если model выбрана без effort, используется default effort модели.
- **FACT:** native `/review` поддерживает отдельный `review_model`; без него используется model текущей session.

## Основной принцип routing

- **PROPOSAL:** route выбирается в порядке `task contract → risk → failure cause → available capability`, а не по номеру фазы или prestige модели.
- **PROPOSAL:** policy хранит **capability classes**, preferred/fallback candidates и reasoning band. Exact model/effort разрешаются effective preflight.
- **PROPOSAL:** verification depth не понижается автоматически при stronger model; сильная модель не заменяет oracle/review.
- **PROPOSAL:** unavailable preferred route приводит к recorded fallback или serialisation, не к выдуманному model slug.

## Task-class routing matrix

| Task class | Примеры | Preferred capability | Reasoning band | Verification/review |
|---|---|---|---|---|
| Deterministic read/transform | Inventory, extract IDs, normalize known format, summarise bounded logs. | **PROPOSAL:** Luna-like; Terra fallback. | Low, иногда Medium. | Schema/count/hash/sample check; reviewer обычно не нужен. |
| Read-heavy exploration | Найти ownership, call graph, relevant tests, reproduce known error. | **PROPOSAL:** Terra-like; Luna для очень узкого поиска. | Medium; High при сложном causality. | Source/file evidence; отделить fact от inference. |
| Scoped implementation | Один vertical ticket с стабильным contract и disjoint zone. | **PROPOSAL:** Terra-like. | Medium default; High для non-local logic. | Focused tests + seam oracle + independent review по риску. |
| Complex implementation/integration | Несколько boundaries, concurrency, migration, compatibility, high ambiguity. | **PROPOSAL:** Sol-like. | High; xhigh/max только после evidence, что High недостаточен и значение доступно. | Multi-level tests, live/edge proof, independent axes. |
| Contract/spec repair | `BLOCKED`, interface ambiguity, reviewer disagreement, plan dependency defect. | **PROPOSAL:** Sol-like researcher/reviewer; Astra-like только hardest cross-system synthesis. | High. | Evidence ledger + fresh adjudication; не писать product code в том же pass. |
| Routine review | Bounded diff against clear contract. | **PROPOSAL:** Terra/Sol-like по сложности. | High, согласно official reviewer guidance. | Read-only + exact findings/evidence. |
| High-risk review | Auth, data loss, security, destructive migration, concurrency, final whole-system critical flow. | **PROPOSAL:** Sol-like; Astra-like optional escalation. | High/Extra High where supported. | Независимые axes + live/negative proof; stronger model не единственный gate. |
| Blind acceptance | Brief против runnable outcome, без внутренних artifacts. | **PROPOSAL:** Sol-like для сложного продукта; Terra-like для bounded project. | Medium/High. | Fresh context, runnable scenarios, requirement-level verdict. |
| Orchestration/state bookkeeping | Validate packet/state, changed paths, ready graph. | **PROPOSAL:** deterministic tool first; Luna/Terra-like only for semantic summary. | Low/Medium. | Machine validator; не тратить frontier model на вычислимое. |

## Risk modifiers

Любой modifier повышает reasoning/review depth, но не обязательно меняет model:

- **PROPOSAL:** irreversible/destructive effect;
- **PROPOSAL:** security/auth/secrets/trust boundary;
- **PROPOSAL:** data migration/loss/corruption;
- **PROPOSAL:** concurrent/distributed behavior;
- **PROPOSAL:** public API/schema/backward compatibility;
- **PROPOSAL:** high blast radius или weak rollback;
- **PROPOSAL:** weak/absent test oracle;
- **PROPOSAL:** cross-platform behavior;
- **PROPOSAL:** contradictory requirements/reviewer verdicts.

**INFERENCE:** risk чаще должен добавлять независимый oracle/reviewer, чем просто поднимать model. V1 major defects оставались при зелёной suite и после capable workers.

## Escalation flow

```text
result not accepted
       │
       ├─ permission/tool/environment? ─> fix authority/environment or re-plan
       ├─ contract/zone/dependency gap? ─> contract repair + new packet/version
       ├─ verification oracle wrong? ────> repair oracle/spec before implementation
       └─ implementation defect
                 │
                 ├─ bounded omission, context still valid ─> same-worker repair
                 └─ repeated class / stuck / saturated context
                             ├─ fresh context, same capability if task was adequate
                             └─ stronger model/effort if complexity caused failure
```

### Retry

- **PROPOSAL:** retry означает повторить transient operation без изменения approach: flaky network/test/tool interruption. Он не должен увеличивать code repair count.
- **PROPOSAL:** retry допустим только при доказанном transient cause и idempotent/safe operation; иначе это repair.
- **PROPOSAL:** повторяющийся identical failure прекращает retry и возвращается на cause triage.

### Repair

- **PROPOSAL:** repair исправляет конкретное accepted finding и добавляет regression proof.
- **PROPOSAL:** same-context repair — для локального underdone при стабильном contract.
- **PROPOSAL:** fresh-context repair — при повторном defect class, changed contract, anchoring, long context или failed approach.
- **OBSERVED:** Idea Scout имел 37 repair на 17 tickets; часть была contract defects. Поэтому единый hard cap и единый счётчик причины искажают routing.

### Stronger-model/effort escalation

- **PROPOSAL:** разрешена, когда evidence указывает на reasoning/complexity failure: неверная multi-boundary synthesis, повторная causal error, incomplete trade-off analysis, либо high-risk adjudication.
- **PROPOSAL:** не использовать для отсутствующих permissions, tools, credentials, dependency readiness, write ownership или user decision.
- **PROPOSAL:** сначала повышать reasoning в доступном task-appropriate class, затем model class — если это дешевле и preflight подтверждает значение. Это hypothesis для eval, не official algorithm.
- **OBSERVED:** fresh Sol High закрыл повторяющиеся проблемы T07 после Terra High, но один run не доказывает универсальную лестницу.

## De-escalation

- **PROPOSAL:** после stabilised contract и доказанного pattern последующие однотипные tickets переводятся на lower-cost class/effort.
- **PROPOSAL:** механические follow-ups, ledger validation и extraction выносятся в Luna/Terra-like path, даже если plan делала stronger model.
- **PROPOSAL:** downgrade не применяется к final independent verification того же high-risk seam только потому, что implementation прошла.
- **PROPOSAL:** после downgrade sample failures возвращают task на previous validated route, а не создают бесконечное oscillation.

## Когда нужен внешний или Astra review

### Подтверждённое

- **FACT:** Astra официально позиционируется для hardest end-to-end work; high reasoning — для сложных review/security задач.
- **FACT:** official docs не устанавливают обязательный Astra или external-review gate.
- **OBSERVED:** Astra architecture/plan reviews Idea Scout нашли важные dependency, zone, interface и coverage defects.
- **INFERENCE:** ценность могла исходить из fresh mandate/independence, stronger model или обоих факторов; corpus не разделяет их.

### Policy candidate

Внешний/Astra review **рассматривается**, когда присутствуют минимум один high-blast-radius signal и один uncertainty signal:

| High-blast-radius | Uncertainty |
|---|---|
| irreversible data/security/public-interface change | reviewers disagree |
| архитектура затрагивает ≥3 независимых boundaries | contract пришлось менять повторно |
| final acceptance критичного продукта | available tests/oracles неполны |
| решение дорого отменить | базовая модель повторила один causal defect |

- **PROPOSAL:** Astra/external review не нужен для routine tickets, deterministic transforms или как ritual после каждого repair.
- **PROPOSAL:** если Astra недоступна, fallback — fresh Sol-like high reasoning + независимый second axis + stronger evidence, не block всего V1.
- **PROPOSAL:** external reviewer получает sanitised minimal packet и read-only access; внешняя отправка/CLI/provider требует явной authority и source/trust assessment.
- **OPEN:** thresholds и экономическая граница должны быть проверены blind eval; пользователь утверждает внешнюю/cost authority.

## Reviewer routing отдельно от worker routing

- **PROPOSAL:** reviewer model не должна автоматически совпадать с worker; independence определяется fresh context/mandate/evidence, не только model name.
- **PROPOSAL:** reviewer reasoning default выше routine worker для non-trivial diff, что согласуется с official `high` guidance.
- **PROPOSAL:** несколько reviewers получают orthogonal axes, а не одинаковый prompt; findings deduplicates orchestrator.
- **PROPOSAL:** disagreement идёт к contract/evidence adjudication; majority vote без анализа не применяется.
- **FACT:** `/review` может использовать `review_model`, но exact availability должна быть подтверждена текущей surface.

## Budget и stop policy

- **FACT:** subagents увеличивают token usage; higher reasoning увеличивает latency/tokens. API pricing не равно Codex plan credits.
- **PROPOSAL:** budgets измерять доступными runtime signals; если их нет, использовать attempts/time/checkpoints как coarse limits и помечать их как такие.
- **PROPOSAL:** reaching a threshold запускает diagnostic checkpoint: status, causes, remaining risk, fallback/user decision. Это не автоматическое объявление «готово» или бесконечное продолжение.
- **PROPOSAL:** parallelism оправдан независимостью и context isolation, а не только скоростью; parallel write-heavy work требует safety proof.

## Подтверждённое против гипотез

| Claim | Статус |
|---|---|
| Native subagents и per-spawn model/effort routing существуют | **FACT** |
| Read-heavy parallelism рекомендован; write-heavy требует осторожности | **FACT** |
| Luna/Terra/Sol/Astra имеют разные официальные task positioning | **FACT** |
| Terra Medium — лучший default именно для Autopilot V1 | **PROPOSAL**, требует eval |
| После одной repair всегда нужен fresh context | **PROPOSAL**, не official fact |
| Две ошибки требуют Sol, три — Astra | **НЕ ПОДТВЕРЖДЕНО / OPEN** |
| Astra review всегда лучше нескольких smaller reviewers | **НЕ ПОДТВЕРЖДЕНО / OPEN** |
| Million-token API context доступен и экономичен в любой Codex surface | **НЕ ПОДТВЕРЖДЕНО** |
| Community workspace exact config/limits применимы | **HYPOTHESIS ONLY** |

## Официальные противоречия и незакрываемые сейчас решения

1. **OPEN:** effort vocabulary: config reference `minimal|low|medium|high|xhigh`; API GPT-5.6 `none|low|medium|high|xhigh|max`; Subagents упоминает `max/ultra`; Models описывает Ultra как multi-agent mode.
2. **OPEN:** exact model availability по plan/rollout/sign-in/client; Codex cloud имеет отдельные ограничения.
3. **OPEN:** `gpt-5.6` alias против pinned `gpt-5.6-sol` для portable config.
4. **OPEN:** deterministic escalation thresholds отсутствуют в docs.
5. **OPEN:** обязательность Astra/external review не документирована.
6. **OPEN:** default subagent concurrency, nesting, timeout/token budget и machine-readable summary schema не фиксированы.
7. **OPEN:** exact fresh-context/inherited-history semantics native subagent не специфицированы.
8. **OPEN:** custom read-only agent может получить parent live override; effective enforcement нужно проверять.
9. **OPEN:** permission profiles Beta и не композируются с legacy sandbox; это safety issue, не routing shortcut.

## Решение для V1

- **PROPOSAL:** зафиксировать task/risk classes, cause triage и fallbacks; не фиксировать universal exact model IDs/effort enum до preflight/evals.
- **PROPOSAL:** надёжное ядро должно работать на current parent model serially; optional models/subagents повышают efficiency/independence, но не являются единственной дорогой к correctness.
- **OPEN:** количественные thresholds, default class и Astra gate переносятся в [08-open-decisions.md](08-open-decisions.md) и следующий runtime experiment/design pass.
