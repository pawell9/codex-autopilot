# Граница V1 `codex-autopilot`

Цель V1 — надёжно провести один scoped software change от intent до проверенного результата в Codex-native среде. Это scope contract для следующего design-pass, не реализация skill.

## Метки

`FACT` — подтверждено; `OBSERVED` — Idea Scout V1; `INFERENCE` — вывод; `PROPOSAL` — граница V1; `OPEN` — ещё требует решения.

Scope выведен из [PROJECT-BRIEF](../PROJECT-BRIEF.md), [used/upstream comparison](01-component-map.md), V1 [review log](../references/idea-scout-v1/run-artifacts/2026-09-05-idea-scout/review-log.md) и current official [Codex evidence index](../references/official/openai-links.md).

## V1 success definition

- **PROPOSAL:** fresh operator может запустить workflow в существующем Git repository, получить preflight, brief/requirements, executable tickets, isolated execution, independent review/repair, blind acceptance и resumable final record.
- **PROPOSAL:** workflow корректно деградирует без subagents/worktrees/preferred model, а не симулирует unavailable capability.
- **PROPOSAL:** после interruption новый orchestrator восстанавливает next safe action только из repository state и git evidence.
- **PROPOSAL:** ни один обычный run не меняет project instructions/configs или внешнее состояние скрыто.

## MUST

### Lifecycle и traceability

- **PROPOSAL:** immutable user-intent brief и requirement ledger с `done/partial/deferred/dropped/placeholder` semantics.
- **PROPOSAL:** явные gates: preflight, requirement completeness, executable plan, per-ticket verify/review, final blind acceptance.
- **OBSERVED:** две G2 editions нашли 18 issues; completeness gate доказал ценность.
- **PROPOSAL:** каждое изменение requirement/contract — versioned amendment с reason/evidence.

### Preflight и capability-based routing

- **PROPOSAL:** проверки из [06-preflight.md](06-preflight.md), включая instructions, dirty state, `.autopilot`, git, permissions, models/efforts, subagents и tools.
- **PROPOSAL:** routing по task/risk capability class и фактической availability, без обязательного model slug.
- **FACT:** official availability и effort vocab зависят от surface/rollout и документированы несогласованно.

### Durable state и resume

- **PROPOSAL:** один валидируемый run ledger под `.autopilot/**` с schema version, state transitions, contract versions, tickets, attempts, findings и checkpoints.
- **PROPOSAL:** atomic/reconstructible checkpoint перед/после material transitions.
- **OBSERVED:** V1 возобновился из files+git; thread/reviewer handles не были durable.
- **PROPOSAL:** no mandatory dashboard/server for state correctness.

### Execution and context isolation

- **PROPOSAL:** один task packet на один observable outcome; fresh worker по умолчанию.
- **PROPOSAL:** compact structured return с changed paths, verification evidence, requirement mapping и blocker type.
- **PROPOSAL:** no full orchestration history in worker context.
- **PROPOSAL:** native subagent path и serial fallback должны сохранять один и тот же semantic contract.

### Write safety

- **PROPOSAL:** Autopilot owns only `.autopilot/**`; project files preserve-by-default.
- **PROPOSAL:** exclusive declared write zones, actual changed-path validation, user dirty-change protection.
- **PROPOSAL:** read-heavy parallel default; concurrent writers только disjoint или isolated; serial fallback.
- **PROPOSAL:** destructive/external/data/cost/access actions имеют отдельный authority gate и rollback/checkpoint.

### Verification, review, repair

- **PROPOSAL:** verification plan у ticket заранее включает подходящий oracle, а не только generic test command.
- **OBSERVED:** V1 green suites пропустили data loss и ineffective guards; live/edge/mutation evidence необходимо для critical seams.
- **PROPOSAL:** independent read-only reviewer; risk-based axes; reviewer не repair.
- **PROPOSAL:** cause-first failure taxonomy отделяет implementation, contract, environment, permission, evidence и orchestration defects.
- **PROPOSAL:** retry/same-context repair/fresh repair/stronger model выбираются после cause triage.
- **PROPOSAL:** final fresh blind acceptance against brief and observable run; `UNVERIFIABLE` допустим и видим.

### Honest completion

- **PROPOSAL:** final report показывает fulfilled, partial/missing, deferred/dropped, placeholders, assumptions, deviations, verification commands/results и remaining risks.
- **PROPOSAL:** completion не объявляется только по worker self-report, green scoped tests или закрытым tickets.

## SHOULD

- **PROPOSAL:** использовать native subagents для independent read-heavy work и bounded ticket execution, когда capability подтверждён.
- **PROPOSAL:** использовать native `/review` там, где его scope/read-only behavior подтверждены, сохраняя portable reviewer contract.
- **PROPOSAL:** explicit worktree isolation для concurrent writers в Git repos после runtime smoke.
- **PROPOSAL:** один logical ticket — один recoverable git checkpoint, если это совместимо с user repo policy.
- **PROPOSAL:** risk classifier для выбора числа review axes и глубины verification.
- **PROPOSAL:** machine validation task/return/ledger schemas; transport adapter может быть простым.
- **PROPOSAL:** budget telemetry по фактически доступным signals; conservative stop/escalation checkpoints.
- **PROPOSAL:** concise reviewer-pattern ledger, чтобы recreated reviewer видел повторяющиеся дефекты без старой chat history.
- **PROPOSAL:** no-git degraded mode хотя бы как явный отказ/ограниченный serial workflow, а не undefined behavior.

## OUT OF V1

| Возможность | Почему откладывается |
|---|---|
| Обязательный HTML dashboard/static server | **INFERENCE:** correctness и resume обеспечиваются ledger; empirical necessity UI не доказана. |
| Полноценный external orchestrator через App Server/SDK | **FACT:** primitives существуют, часть API experimental; skill-first V1 не требует отдельного runtime. |
| Custom-agent TOML library | **FACT:** формат может эволюционировать; роли сначала должны быть проверены семантически. |
| Beta permission profiles как обязательная основа | **FACT:** Beta, conflict с legacy sandbox, per-agent semantics не полны. |
| Experimental context management/memories как dependency | **FACT:** availability ограничена; memories не authoritative store. |
| Автоматическое редактирование `AGENTS.md`/`.codex`/`.agents`/`CLAUDE.md` | **FACT+PROPOSAL:** project-owned/protected; отдельный opt-in deliverable позже. |
| ADR generation и постоянная project memory | **INFERENCE:** полезны, но расширяют write scope за core change; вынести в optional post-acceptance workflow. |
| Polish loop | **OBSERVED:** в V1 corpus не валидирован; оставить отдельным later experiment. |
| Scheduled/night/unattended automation | **INFERENCE:** требует зрелой authority, telemetry и failure recovery; community workspace — не technical truth. |
| Plugin/package distribution | **INFERENCE:** сначала доказать workflow contract как skill; distribution design позже. |
| Universal support всех project types/surfaces | **FACT:** цель проекта — надёжный собственный workflow, не platform. |
| Автоматический security scanner/Codex Security integration | **FACT:** official capability существует, но coverage/cost/gating для V1 не исследованы. Risk-specific reviewer остаётся. |
| Exact cost optimizer / hard token budgets | **FACT:** Codex credits/API pricing/surface metrics различаются; portable точность не доказана. |
| Proactive nested agent swarms / Ultra dependency | **FACT:** limits и semantics неоднозначны; большинство задач, по docs, не требует Max/Ultra. |
| Automatic deployment, messaging, production migrations | **PROPOSAL:** outside core authority boundary. |

## Сознательные упрощения V1

- **PROPOSAL:** поддерживать одну active run ownership на workspace; multi-run concurrency позже.
- **PROPOSAL:** parallelise read-heavy задачи; writers serial by default до доказанной isolation.
- **PROPOSAL:** task classes и fallback chain вместо тонкой матрицы каждого model slug.
- **PROPOSAL:** один portable context/return contract поверх разных transports.
- **PROPOSAL:** role mandates в документации/state, без требования custom-agent configs.
- **PROPOSAL:** status/report в Markdown/ledger достаточно; UI projection не часть acceptance.
- **PROPOSAL:** thresholds вызывают diagnostic checkpoint, но не автоматический endless loop и не arbitrary fail.

## Не переносить из Idea Scout как универсальное правило

- **OBSERVED:** Sol High помог после повторных Terra repairs, но один run не доказывает универсальную лестницу `Terra → Sol → Astra`.
- **OBSERVED:** три финальных reviewers были оправданы T3-риск-профилем, но не доказаны как минимум для каждого ticket.
- **OBSERVED:** explicit worktrees исправили проблему конкретного hybrid bridge; native Codex behavior ещё нужно проверить.
- **OBSERVED:** 17 tickets/7 waves/37 repairs описывают Idea Scout, не нормы V1.
- **PROPOSAL:** использовать эти данные как regression scenarios для будущих evals.

## Exit criteria design-pass перед implementation

Следующий этап может перейти к реализации только если:

- **PROPOSAL:** согласована одна state machine с legal transitions и recovery;
- **PROPOSAL:** закрыт или экспериментально ограничен каждый safety-critical OPEN из [08](08-open-decisions.md);
- **PROPOSAL:** schemas task/return/checkpoint/write lease определены и валидируемы;
- **PROPOSAL:** есть test matrix минимум для new run, resume, contract defect, permission failure, dirty overlap, reviewer disagreement и green-but-broken live case;
- **PROPOSAL:** routing fallback работает без Astra, custom agents, permission profiles и dashboard.

## Scope verdict

- **INFERENCE:** надёжная Codex-native V1 достижима без переписывания всего upstream один-в-один.
- **PROPOSAL:** ядро — evidence/state/contracts/safety/review; native agents/models — заменяемые execution resources.
- **OPEN:** ledger format, precise git protocol и quantitative routing thresholds остаются для следующего design/experiment этапа.
