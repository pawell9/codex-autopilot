# Open decisions

Здесь только решения, которых evidence пока недостаточно закрыть. Предложения в остальных документах не превращают эти пункты в факты.

## Метки

`FACT` — подтверждённый constraint; `OBSERVED` — один V1-run; `INFERENCE` — вывод; `PROPOSAL` — кандидат; `OPEN` — предмет решения.

Общие evidence anchors: [project intent](../PROJECT-BRIEF.md), [V1 review log](../references/idea-scout-v1/run-artifacts/2026-09-05-idea-scout/review-log.md), [V1 state](../references/idea-scout-v1/runtime-state/state.js), [official source/conflict register](../references/official/openai-links.md) и [community hypotheses](../references/community/).

## OD-01 — формат durable run ledger

- **Вопрос / OPEN:** JSON, JSONL event log, YAML или Markdown+machine section; нужен ли append-only event log плюс materialized state?
- **Почему открыт:** upstream `state.js` полезен, но хрупко редактируется и смешан с dashboard snapshot/server. Сравнительных runtime eval нет.
- **Варианты:** (A) schema-versioned JSON snapshot; (B) append-only JSONL + derived snapshot; (C) Markdown front matter/sections + validator.
- **Evidence:** **OBSERVED:** `state.js` сохранил requirements, 37 repairs, 7 handoffs и resume context. **INFERENCE:** JS-as-data и anchored edits не нужны Codex-native ядру.
- **Проверить позже:** atomic writes, recovery после partial write, diff readability, schema migrations, concurrent orchestrator guard.
- **Кто решает:** **design-agent**, затем **runtime experiment**.

## OD-02 — discovery доступных models/efforts

- **Вопрос / OPEN:** как portable preflight получает effective catalog и валидные effort для app/CLI/IDE/cloud?
- **Почему открыт:** official docs говорят о plan/rollout/client differences, но не дают одного универсального capability endpoint; vocab reasoning противоречив.
- **Варианты:** (A) native runtime introspection/tool; (B) documented CLI status/model probe; (C) optimistic spawn с safe fallback и recorded rejection; (D) user-provided capability profile.
- **Evidence:** **FACT:** `minimal/none/max/ultra` и `gpt-5.6`/`gpt-5.6-sol` описаны несогласованно ([Models](https://learn.chatgpt.com/docs/models), [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents), [Configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)).
- **Проверить позже:** конкретные supported clients/versions; non-interactive behavior; inheritance after failed override.
- **Кто решает:** **runtime experiment**; design-agent задаёт fallback protocol.

## OD-03 — quantitative retry/repair/escalation policy

- **Вопрос / OPEN:** после скольких и каких failures оставаться в том же context, переходить fresh, усиливать model/effort или возвращать contract на redesign?
- **Почему открыт:** docs дают качественные task classes, но не algorithm; V1 один и смешивает 37 attempts разных causes.
- **Варианты:** (A) one bounded same-context repair, затем cause checkpoint; (B) thresholds по defect class/risk; (C) eval-derived policy; (D) user-configured budget.
- **Evidence:** **OBSERVED:** repeated same-class Terra repairs не помогали T07, fresh Sol помог; многие `BLOCKED` были contract defects и не должны считаться failure worker. Upstream universal cap был превышен.
- **Проверить позже:** labelled replay/eval Idea Scout cases; latency/quality/cost; stop behavior при environment/permission failure.
- **Кто решает:** **design-agent + runtime experiment**; пользователь задаёт budget preference, если material.

## OD-04 — когда нужен Astra или внешний review

- **Вопрос / OPEN:** какие risk/complexity signals делают Astra/external reviewer оправданным или обязательным?
- **Почему открыт:** official docs называют Astra strongest для hardest work, но не определяют review gate; availability не гарантирована. External CLI добавляет trust/context/cost boundary.
- **Варианты:** (A) никогда mandatory, только optional escalation; (B) risk-triggered architecture/final review; (C) reviewer disagreement adjudication; (D) user-request only.
- **Evidence:** **OBSERVED:** Astra reviews Idea Scout нашли существенные architecture/plan defects. **FACT:** один case не доказывает superiority или universal necessity; current official guidance не задаёт threshold.
- **Проверить позже:** blind comparative reviews на одном corpus, false-positive/coverage/cost, availability fallback.
- **Кто решает:** **runtime experiment**, затем **user** утверждает policy/cost boundary.

## OD-05 — review topology по risk class

- **Вопрос / OPEN:** когда достаточно одного reviewer, когда нужны независимые axes, и является ли `/review` эквивалентом reviewer subagent?
- **Почему открыт:** upstream фиксирует два persistent reviewers; V1 финально потребовал 3+3; official docs предлагают multi-axis examples, не minimum.
- **Варианты:** (A) one combined reviewer default; (B) risk matrix добавляет security/data/UX axes; (C) always two; (D) native `/review` + targeted subagents.
- **Evidence:** **OBSERVED:** разные мандаты находили разные defects, disagreement обнаружил contract gap. **FACT:** `/review` read-only и имеет model override, но transport/scope vary by surface ([Code review](https://learn.chatgpt.com/docs/code-review)).
- **Проверить позже:** seeded defect suite, independence/anchoring, native `/review` outputs и re-review continuity.
- **Кто решает:** **design-agent + runtime experiment**.

## OD-06 — enforcement read-only reviewers и write zones

- **Вопрос / OPEN:** какой минимум technical enforcement нужен поверх instructions?
- **Почему открыт:** standard sandbox не знает logical zones; custom read-only может быть overridden parent live permissions; granular permission profiles Beta.
- **Варианты:** (A) effective read-only sandbox + post-diff; (B) clean snapshot/worktree + zero-diff validation; (C) Beta path profiles with fallback; (D) instruction-only — недостаточен для high-risk.
- **Evidence:** **FACT:** `.git/.agents/.codex` protected, обычные source paths — нет; permission profiles не композируются с legacy sandbox ([Agent approvals & security](https://learn.chatgpt.com/docs/agent-approvals-security), [Permissions](https://learn.chatgpt.com/docs/permissions)).
- **Проверить позже:** child effective policy under `/permissions` overrides; path profile behavior per surface; undeclared-write detector.
- **Кто решает:** **runtime experiment**, design-agent выбирает safe fallback.

## OD-07 — git/worktree strategy

- **Вопрос / OPEN:** serial shared tree, native managed worktrees или explicit CLI worktrees; кто владеет commits/integration?
- **Почему открыт:** V1 evidence относится к hybrid bridge; official managed worktrees имеют surface-specific lifecycle и detached semantics.
- **Варианты:** (A) serial writers in main tree; (B) explicit orchestrator worktree per concurrent ticket; (C) app-managed worktree per chat; (D) hybrid by surface.
- **Evidence:** **OBSERVED:** auto-cleaned background worktree сломал ожидаемую isolation; explicit worktrees+checkpoint commits работали. **FACT:** worktrees разделяют Git metadata, branch cannot be checked out twice ([Worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees)).
- **Проверить позже:** background native subagent lifecycle, ignored files, approvals, cleanup, conflicts, resume across clients.
- **Кто решает:** **runtime experiment**, затем **design-agent**.

## OD-08 — native subagent return и fresh-context semantics

- **Вопрос / OPEN:** достаточно ли native summary transport или нужен `codex exec --output-schema` adapter; что именно означает fresh для spawned thread?
- **Почему открыт:** official docs не задают universal summary schema, max lifetime/nesting или inherited conversation detail.
- **Варианты:** (A) packet + prose summary validator/re-request; (B) non-interactive schema adapter; (C) future native structured contract; (D) file-based return artifact.
- **Evidence:** **FACT:** subagents return summaries; `codex exec` validates final JSON only in its own mode. **OBSERVED:** old bridge required copied boundary rules, но current native inheritance не проверена на этом workflow.
- **Проверить позже:** instruction visibility, history inheritance, malformed return recovery, cancellation/resume.
- **Кто решает:** **runtime experiment**; design-agent сохраняет transport-neutral schema.

## OD-09 — depth/mode model

- **Вопрос / OPEN:** сохранить T0–T3/manual/full или заменить risk/complexity dimensions?
- **Почему открыт:** corpus содержит только один manual T3 run; нет evidence поведения остальных режимов.
- **Варианты:** (A) retain tiers as UX shorthand; (B) risk dimensions independently control tickets/reviews/oracles; (C) two modes: standard/high-risk; (D) auto recommendation + user override.
- **Evidence:** **OBSERVED:** exact ticket/repair counts T3 не следовали нормативам; **INFERENCE:** one scalar tier плохо выражает security, data, UX и integration risk одновременно.
- **Проверить позже:** retrospective classification нескольких projects; predictability and user comprehension.
- **Кто решает:** **design-agent**, пользователь подтверждает UX semantics.

## OD-10 — edits durable project memory/instructions

- **Вопрос / OPEN:** должен ли accepted run предлагать/выполнять обновление `AGENTS.md`, docs и ADRs?
- **Почему открыт:** upstream делает это частью landing; brief требует protect project-owned files; official memories не являются authoritative store.
- **Варианты:** (A) никогда в V1; (B) report-only suggestions; (C) explicit opt-in post-acceptance ticket with diff/review; (D) user-configured allowlist.
- **Evidence:** **OBSERVED:** run-local files+git хватило для resume. **FACT:** Codex reads AGENTS chain once per run и `.agents/.codex` protected в standard workspace-write.
- **Проверить позже:** value of generated memory, staleness risk, instruction size/precedence, ownership expectations.
- **Кто решает:** **user** задаёт policy; design-agent реализует только explicit path. Для V1 current proposal — out of scope.

## OD-11 — no-git support

- **Вопрос / OPEN:** V1 blocks вне Git или предоставляет ограниченный serial workflow?
- **Почему открыт:** commits/worktrees и Idea Scout resume evidence завязаны на Git, но Codex может работать с обычным workspace; продуктовая цель не говорит «Git only» явно.
- **Варианты:** (A) Git hard prerequisite; (B) no-git with file hashes/backups and no concurrent writes; (C) initialize Git only by explicit user request.
- **Evidence:** **FACT:** app worktrees и default `codex exec` flow ожидают Git. **INFERENCE:** безопасный rollback/no-diff proof без Git требует отдельного механизма, которого baseline нет.
- **Проверить позже:** пользовательские use cases и минимальный recoverable snapshot protocol.
- **Кто решает:** **user + design-agent**.

## OD-12 — version/support floor и feature probing

- **Вопрос / OPEN:** фиксировать minimum Codex version или полностью опираться на capability probes?
- **Почему открыт:** docs меняются без per-page dates; features отличаются по surface и maturity; strict version floor может не отражать managed clients.
- **Варианты:** (A) minimum tested versions + probes; (B) probes only; (C) narrow supported surface V1.
- **Evidence:** **FACT:** multi-agent stable/on by default в current local releases, но config может выключить; permission profiles/context management имеют Beta/Experimental maturity.
- **Проверить позже:** доступность version/status signals, regression matrix across clients, failure messages.
- **Кто решает:** **design-agent + runtime experiment**; пользователь выбирает breadth поддержки.

## Приоритет закрытия

1. **OPEN / safety-critical:** OD-06, OD-07, OD-01.
2. **OPEN / execution-critical:** OD-02, OD-08, OD-11, OD-12.
3. **OPEN / quality/economics:** OD-03, OD-04, OD-05, OD-09.
4. **OPEN / post-acceptance policy:** OD-10.

До implementation должны быть закрыты или иметь conservative fallback OD-01/02/03/05/06/07/08/11/12. Astra, project-memory edits и advanced modes не должны блокировать надёжное ядро V1.
