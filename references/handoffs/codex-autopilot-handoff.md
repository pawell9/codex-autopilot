# HANDOFF: перенос Autopilot на полностью Codex-native оркестрацию

## 1. Контекст

Я развиваю собственный подход к агентской разработке и сейчас использую skill **Autopilot** как методологию полного цикла разработки проектов.

Исходный публичный репозиторий Autopilot:

`nick-vels/skills`

Skill расположен примерно здесь:

`skills/autopilot/`

Это тот Autopilot, в котором используются:

- режимы `full / semi / interview / manual`;
- глубина `strict / deep`;
- `.autopilot/state.js`;
- `manifest.md`;
- `interfaces.md`;
- разбиение разработки на фазы;
- briefing;
- specification;
- planning;
- tickets;
- waves;
- subagents;
- review;
- acceptance;
- project memory;
- polish;
- gates;
- zones;
- handoff;
- принцип `one ticket → one context`;
- принцип `one ticket → one commit`.

Autopilot уже использовался мной на реальном проекте и показал себя хорошо.

Главная задача сейчас — **не перепридумать методологию**, а создать на её основе собственный skill, оптимизированный исключительно под Codex и современные модели OpenAI.

Рабочее название:

`codex-autopilot`

Это должен быть отдельный skill, а не хаотичная модификация существующего оригинала.

---

# 2. Почему вообще появился этот проект

До этого схема разработки была гибридной.

Условно:

```text
Claude Code
    ↓
Autopilot orchestrator
    ↓
Codex executors
```

Для связи использовались разные способы, включая прямой `codex exec`, плагины и эксперименты с bridge.

На практике выяснилось, что:

1. Codex хорошо справляется с implementation-задачами.
2. Главный Claude-контекст сильно разрастается.
3. Bridge добавляет лишний слой сложности.
4. Возникает зависимость от двух разных агентных систем.
5. Codex теперь сам способен быть не только исполнителем, но и оркестратором.
6. В Codex есть/развиваются механизмы subagents, отдельных agent threads, model/reasoning routing и т. п.

Поэтому решили рассмотреть архитектуру:

```text
Codex orchestrator
        ↓
Codex subagents
```

без Claude Code как обязательного слоя.

---

# 3. Основное принятое решение

Нужно создать **отдельный Codex-native вариант Autopilot**.

Не переписывать методологию с нуля.

Предварительная оценка:

**примерно 75–85% оригинальной методологии можно сохранить.**

Главное изменение — execution/orchestration layer.

То есть:

```text
ORIGINAL AUTOPILOT
        │
        │ methodology
        ▼
CODEX AUTOPILOT
        │
        ├── Codex-only
        ├── native subagents
        ├── model routing
        ├── reasoning routing
        ├── persistent reviewers
        ├── context isolation
        └── no Claude bridge
```

---

# 4. Целевая архитектура

Основная схема:

```text
┌──────────────────────────────────────┐
│          MAIN ORCHESTRATOR           │
│                                      │
│   GPT-5.6 Sol High / Extra High      │
│   либо Astra в подходящей роли       │
└──────────────────┬───────────────────┘
                   │
                   ▼
             CODEX AUTOPILOT
                   │
          анализ ready tickets
                   │
          complexity routing
                   │
       ┌───────────┼───────────┐
       ▼           ▼           ▼
   Codex worker Codex worker Codex worker
   cheaper model cheaper      stronger
       │           │           │
       └───────────┴───────────┘
                   │
           structured results
                   │
                   ▼
             ORCHESTRATOR
                   │
           review / integration
                   │
                   ▼
              next wave
```

Главный оркестратор **не должен становиться универсальным кодером, который выполняет всё самостоятельно**.

Его основные обязанности:

- понимать состояние Autopilot;
- читать manifest/spec/interfaces;
- определять готовые tickets;
- выбирать worker tier;
- выбирать reasoning effort;
- запускать subagents;
- следить за зонами записи;
- собирать краткие результаты;
- разрешать blockers;
- запускать review;
- принимать решение о следующей wave;
- вести `.autopilot` state;
- делать escalation при необходимости.

---

# 5. Model routing

Одна из главных новых возможностей нашего варианта — маршрутизация задач между моделями.

Не нужно использовать самую дорогую модель для каждого implementation ticket.

Примерная концепция:

```text
LOW
→ дешёвый/быстрый Codex worker

NORMAL
→ основной Codex worker

HARD
→ более сильная модель / повышенный reasoning

ARCHITECTURAL
→ Sol High / Extra High / Astra
→ либо остаётся у orchestration/review уровня
```

Рабочая концепция tiers:

```text
T0
простые механические задачи

T1
обычная реализация

T2
сложная реализация

T3
сложная архитектура / высокий риск

ESCALATION
Sol High / Extra High / Astra
```

Не считать финальные названия моделей зафиксированными.

При разработке skill нужно отдельно проверить актуальные модели Codex/OpenAI и доступные значения reasoning effort.

Ключевой принцип:

**worker не должен сам выбирать себе модель. Маршрутизацию определяет orchestrator/skill.**

---

# 6. Что сохраняем из оригинального Autopilot

Следующие части считаются ценным ядром и не должны выбрасываться без серьёзной причины:

- Manifest требований.
- Briefing.
- Specification.
- Gates.
- Tiering проекта.
- Planning.
- Tickets.
- Dependencies.
- Waves.
- Zones.
- `interfaces.md`.
- Контракты между задачами.
- `one ticket → one fresh worker context`.
- HANDOFF при разрастании worker-контекста.
- `one ticket → one commit`.
- `.autopilot/state.js`.
- Dashboard/state tracking.
- Review.
- Несколько осей review.
- Final acceptance.
- Project memory.
- Polish.

Особенно важно сохранить:

## Waves

Параллельно запускаются только задачи, которые действительно независимы.

## Zones

Два параллельных write-heavy worker не должны иметь пересекающихся write-зон.

## interfaces.md

Это один из ключевых механизмов, позволяющих разрабатывать части системы параллельно и минимизировать передачу лишнего контекста.

---

# 7. Один из ключевых принципов — context isolation

Нельзя тащить полный диалог каждого worker обратно в orchestration context.

Worker может использовать большой локальный контекст, но наружу возвращает только компактный structured contract.

Пример:

```text
STATUS
FILES
TESTS
INTERFACES
REQUIREMENTS
CONCERNS
BLOCKERS
COMMIT
```

Условно worker мог потратить 20–50k токенов, но orchestrator должен получить только короткое резюме результата.

То есть:

```text
WORKER INTERNAL CONTEXT
        ↓
   НЕ ПЕРЕДАЁМ
        ↓
RETURN CONTRACT
        ↓
ORCHESTRATOR
```

Это принципиально важно для борьбы с context bloat.

---

# 8. Review agents

У оригинального Autopilot хорошая идея с отдельными reviewer-контекстами.

Её нужно сохранить и адаптировать под Codex.

Возможная архитектура:

```text
Orchestrator
    │
    ├── executor threads
    │
    ├── spec reviewer
    │
    ├── craft/code reviewer
    │
    └── final acceptance reviewer
```

Некоторые reviewer-контексты имеет смысл держать дольше одного ticket, чтобы они видели накопленные архитектурные противоречия.

Например:

```text
Reviewer A
Manifest + Spec + architectural consistency

Reviewer B
Code quality / craft / implementation quality
```

Reviewer желательно делать read-only, если он только оценивает работу.

Если требуются исправления — создаётся отдельный repair flow/worker.

---

# 9. Роль Astra

Astra рассматривается как сильная модель/агент, которой в дальнейшем можно будет поручить существенную часть проектирования и реализации самого `codex-autopilot`.

Но Astra не обязательно должна постоянно выполнять всю routine orchestration.

Возможная роль:

```text
Sol High
→ основной orchestrator

Astra
→ architecture
→ сложные решения
→ second opinion
→ wave review
→ final review
→ разработка самого skill
```

То есть сильнейшая модель используется там, где дополнительное reasoning действительно окупается.

При этом окончательное распределение ролей между Sol High / Extra High / Astra нужно определить уже при проектировании.

---

# 10. Необходимое изменение Phase 5 / Subagents

В оригинальном Autopilot Phase 5 уже очень близок к нужной архитектуре:

- orchestrator dispatches;
- orchestrator не пишет implementation code;
- ticket уходит в отдельный context;
- результат возвращается компактно.

Но в нашем варианте Phase 5 должен стать Codex-native.

Вместо абстрактного:

```text
spawn subagent
```

нужен полноценный routing pipeline:

```text
READY TICKET
     ↓
CLASSIFY COMPLEXITY
     ↓
SELECT AGENT ROLE
     ↓
SELECT MODEL TIER
     ↓
SELECT REASONING
     ↓
CHECK WRITE ZONE
     ↓
SPAWN CODEX SUBAGENT
     ↓
WAIT / RECEIVE RETURN CONTRACT
     ↓
REVIEW
```

Особенно важно формализовать правила параллелизма.

Например:

```text
Если ≥2 ready tickets имеют независимые dependencies
и непересекающиеся write zones,
они могут быть выполнены параллельно.
```

И наоборот:

```text
если write zones пересекаются,
они не должны исполняться одновременно.
```

---

# 11. Codex-only

Новый skill должен быть сознательно **Codex-only**.

Не нужна универсальность оригинального Autopilot под:

- Claude Code;
- Cursor;
- Codex;
- произвольные harness.

Это позволяет сильно упростить skill.

Например:

вместо:

```text
CLAUDE.md / AGENTS.md detection
```

можно ориентироваться прежде всего на Codex-native инфраструктуру:

```text
AGENTS.md
Codex skills
Codex agents
Codex config
```

Конкретную поддержку project-level/global-level инструкций нужно сверять с актуальной документацией Codex на момент разработки.

---

# 12. Предварительная структура нового skill

Ориентировочная структура:

```text
codex-autopilot/
│
├── SKILL.md
│
├── phases/
│   ├── 0-preflight.md
│   ├── 0-modes.md
│   ├── 0-instruments.md
│   ├── 0-memory.md
│   ├── 1-manifest.md
│   ├── 2-briefing.md
│   ├── 3-spec.md
│   ├── 4-plan.md
│   ├── 5-subagents.md
│   ├── 5-repair.md
│   ├── 6-review.md
│   ├── 7-instruments.md
│   ├── 8-final.md
│   ├── 9-memory.md
│   └── polish.md
│
├── prompts/
│   ├── executor.md
│   ├── spec-reviewer.md
│   ├── craft-reviewer.md
│   └── acceptance-reviewer.md
│
├── routing/
│   ├── models.md
│   └── complexity.md
│
└── tests/
```

Это не утверждённая финальная структура.

Её можно изменить после полноценного design/research этапа.

---

# 13. Очень важный вопрос безопасности

Новый skill нельзя разрабатывать прямо внутри текущего боевого проекта.

Нужно использовать **физическую изоляцию**, а не просто надеяться, что агент не удалит файлы.

Целевая схема:

```text
CURRENT PROJECT
idea-scout/
│
├── исходники
├── AGENTS.md
├── .claude/
├── .codex/
├── .autopilot/
└── ...
        │
        │ reference only
        ▼

SEPARATE REPOSITORY
codex-autopilot/
│
├── SKILL.md
├── phases/
├── prompts/
├── routing/
├── tests/
└── fixtures/
        │
        ▼
DISPOSABLE TEST PROJECTS
```

Текущий продукт нельзя использовать как рабочую директорию разработки skill.

---

# 14. Как сохранить текущий проект

Перед началом разработки `codex-autopilot` текущий проект необходимо довести до стабильного frozen-состояния:

```text
complete project
     ↓
tests
     ↓
git status clean
     ↓
final commit
     ↓
tag/checkpoint
     ↓
push/backup
```

После этого оригинальная рабочая копия считается защищённой.

Если новый skill нужно протестировать на реальном проекте:

```text
original project
      ↓
clone / isolated worktree
      ↓
test copy
      ↓
codex-autopilot experiment
```

Если эксперимент ломает проект:

```text
delete test copy
→ recreate
```

Оригинал остаётся нетронутым.

---

# 15. Ownership principle

Очень важный архитектурный принцип для самого skill:

> Skill owns only its namespace. Everything else is project-owned.

Например Autopilot свободно управляет:

```text
.autopilot/**
```

Но следующие вещи по умолчанию принадлежат проекту:

```text
AGENTS.md
.claude/**
.codex/**
.github/**
.git/**
existing skills
system/project configuration
```

Они должны быть:

```text
READ / PRESERVE BY DEFAULT
```

Если требуется их изменить, это должно быть отдельным осознанным действием, а не побочным эффектом Autopilot.

---

# 16. Destructive action policy

В новом skill нужно отдельно формализовать destructive-action policy.

Без явной необходимости нельзя:

```text
rm -rf repository root
git clean -fd
git clean -fdx
git reset --hard
удалять .git
удалять AGENTS.md
удалять .claude/
удалять .codex/
удалять существующие skills
перезаписывать системные конфиги проекта целиком
```

Но предпочтительно не просто запрещать конкретные shell-команды, а проектировать права через allowlist/write ownership.

---

# 17. Права разных ролей

Нужно рассмотреть role-based write policy.

## Planning phase

```text
READ project
WRITE .autopilot/**
NO implementation changes
NO destructive actions
```

## Executor

```text
READ required project context
WRITE only ticket zone
WRITE related tests
NO writes outside assigned zone
```

## Orchestrator

```text
READ project
WRITE .autopilot/**
manage orchestration state
git status/diff/checks
```

При этом orchestrator по умолчанию не должен писать implementation code.

## Reviewer

По возможности:

```text
READ ONLY
```

## Repair worker

Получает ограниченную write-zone только для конкретного исправления.

---

# 18. Preflight / doctor

В новый skill желательно встроить предварительную диагностику среды.

Перед большим запуском Autopilot должен проверить хотя бы:

- доступна ли нужная Codex functionality;
- можно ли запускать subagents;
- какие модели доступны;
- какие reasoning effort доступны;
- можно ли назначать модель subagent;
- доступна ли параллельность;
- есть ли git;
- clean/dirty working tree;
- существует ли AGENTS.md;
- существует ли `.autopilot`;
- нет ли незавершённого предыдущего run;
- есть ли необходимые инструменты проекта.

Это особенно важно, потому что capabilities Codex могут со временем меняться.

Нельзя жёстко предполагать наличие capability, не проверив её.

---

# 19. Нужно изучить актуальную документацию OpenAI

Перед окончательным проектированием skill обязательно провести отдельное исследование актуальной документации OpenAI/Codex.

Особенно интересуют:

- prompting новых моделей;
- agentic prompting;
- Codex subagents;
- custom agents;
- model selection;
- reasoning effort;
- context management;
- skills;
- AGENTS.md;
- tool-use instructions;
- parallel agents;
- delegation;
- long-running agent workflows;
- review patterns;
- safe agent actions;
- instruction hierarchy;
- prompt conflicts.

Нельзя просто механически перенести prompts старого Autopilot.

Нужно адаптировать их под современные модели OpenAI.

---

# 20. Предпочтительный стиль инструкций нового skill

Мы пришли к идее, что новый Autopilot должен быть более контрактным и формальным.

Предпочтительная структура:

```text
CONTRACT
↓
INVARIANTS
↓
CURRENT PHASE
↓
ALLOWED ACTIONS
↓
FORBIDDEN ACTIONS
↓
INPUT
↓
OUTPUT CONTRACT
↓
COMPLETION CRITERIA
```

Предпочитать короткие проверяемые invariants длинным философским инструкциям.

Например:

```text
Two parallel workers MUST NOT have overlapping write zones.
```

лучше, чем несколько абзацев объяснения причин.

Другой пример:

```text
Worker MUST NOT modify files outside its ticket zone.
```

Это должно быть жёстким правилом.

---

# 21. Instruction hierarchy

При проектировании нужно специально определить приоритет инструкций, чтобы skill не конфликтовал с project/user instructions.

Предварительная идея:

```text
User explicit instructions
        ↓
Project-level instructions / AGENTS.md
        ↓
Codex Autopilot invariants
        ↓
Current phase rules
        ↓
Ticket-specific instructions
```

Но точную hierarchy нужно сверить с реальной актуальной системой Codex/OpenAI.

Skill не должен случайно создавать конфликтующие инструкции.

---

# 22. Structured task metadata

Tickets нового Autopilot можно расширить metadata.

Например:

```text
complexity:
  low | normal | hard | architectural

worker_tier:
  cheap | standard | strong

reasoning:
  low | medium | high

write_zone:
  [...]

dependencies:
  [...]

wave:
  N
```

Autopilot state также потенциально может хранить:

```text
Task 07
worker: codex
model-tier: standard
reasoning: medium
attempt: 1
```

Это позволит позже анализировать эффективность orchestration.

Например:

- какие задачи регулярно требуют escalation;
- где дешёвая модель справляется;
- где приходится делать повторный repair;
- какие типы задач зря отправляются сильным моделям;
- расход reasoning/model tier по типам задач.

---

# 23. Будущий self-improvement / telemetry

Это не обязательный V1-функционал, но хороший потенциальный следующий слой.

Можно собирать статистику:

```text
task complexity
model tier
reasoning
attempts
review failures
repair count
success/failure
```

И на её основе со временем улучшать routing policy.

Не нужно усложнять этим первую версию, но архитектура не должна закрывать такую возможность.

---

# 24. Происхождение и лицензия

Исходный `nick-vels/skills` опубликован под MIT License.

Поэтому можно создавать собственную модифицированную версию при соблюдении условий лицензии.

В нашем skill нужно корректно сохранить attribution/license notice.

Например:

```text
Based on Autopilot by Nick Vels
MIT License
Upstream: nick-vels/skills
```

Точную формулировку оформить при реализации.

---

# 25. Как должен разрабатываться сам codex-autopilot

Предлагаемый процесс:

```text
1. Freeze текущий production project.

2. Создать отдельный repository:
   codex-autopilot.

3. Собрать входные материалы:
   - upstream Autopilot;
   - этот handoff;
   - актуальная документация OpenAI/Codex;
   - наблюдения из реальной разработки;
   - требования безопасности.

4. Research.

5. Architecture/design.

6. Specification.

7. Implementation.

8. Synthetic fixture projects.

9. Tests.

10. Test на disposable clone реального проекта.

11. Review.

12. Acceptance.

13. v1.0.

14. Global installation/use.
```

Не переходить сразу к редактированию `SKILL.md` без architecture/design этапа.

---

# 26. Astra как агент для разработки самого skill

Есть идея передать большую часть конечной реализации Astra.

Но ей нужно дать не просто:

> «переделай Autopilot под Codex».

Ей нужно передать:

```text
1. upstream Autopilot
2. этот handoff / отдельный brief
3. актуальную документацию Codex
4. target architecture
5. safety invariants
6. model-routing goals
```

После этого Astra должна сначала провести анализ и предложить архитектуру.

Только затем — реализацию.

Желательно не переносить в неё весь огромный исторический чат, если достаточно структурированного handoff.

---

# 27. Что НЕ нужно делать

Не следует:

- переписывать Autopilot с нуля без необходимости;
- превращать старый skill в смесь Claude/Codex-specific логики;
- делать главный Codex-чат исполнителем всех задач;
- использовать сильнейшую модель для каждой мелочи;
- передавать полные worker conversations обратно orchestrator;
- разрешать двум workers одновременно писать одни файлы;
- тестировать новый skill на единственной рабочей копии production project;
- давать Autopilot право свободно удалять системные файлы проекта;
- предполагать capabilities Codex без preflight;
- механически копировать старые prompts без проверки актуальных рекомендаций OpenAI.

---

# 28. Что пока НЕ зафиксировано окончательно

Следующие вопросы остаются предметом следующего этапа проектирования:

1. Точная модель главного orchestrator.
2. Когда использовать Sol High, Extra High и Astra.
3. Конкретная таблица worker tiers.
4. Точные reasoning-effort levels.
5. Максимальное количество параллельных workers.
6. Нужны ли отдельные persistent reviewers.
7. Когда делать automatic escalation.
8. Нужен ли repair-agent как отдельная роль.
9. Финальный формат task metadata.
10. Нужно ли сохранять все оригинальные phases один-в-один.
11. Финальная структура файлов skill.
12. Насколько сложным делать doctor/preflight.
13. Как именно запускать real-world acceptance.
14. Нужно ли делать telemetry уже в V1.
15. Какие Codex-native capabilities на текущую дату реально доступны и стабильны.

Не считать предыдущие черновые решения по этим вопросам жёсткими требованиями.

---

# 29. Главная продуктовая идея

`codex-autopilot` — это не просто prompt для запуска нескольких агентов.

Это полноценный **orchestration methodology skill**, который превращает один сильный Codex-контекст в управляющий слой над несколькими специализированными Codex-контекстами.

Ключевые свойства:

```text
PLAN centrally
EXECUTE distributively
ISOLATE context
CONTROL writes
ROUTE models
REVIEW independently
PRESERVE project state
ESCALATE intelligently
```

То есть:

```text
Strong intelligence where needed
+
cheap execution where sufficient
+
strict architectural control
+
minimal context pollution
```

---

# 30. Главная цель

Получить систему, в которой пользователь может запустить Autopilot на достаточно большом software-проекте, а дальше:

```text
orchestrator
→ понимает цель
→ строит spec
→ строит plan
→ создаёт tickets
→ формирует waves
→ распределяет workers
→ подбирает модели
→ контролирует interfaces
→ принимает результаты
→ запускает review
→ исправляет проблемы
→ выполняет acceptance
→ обновляет project memory
```

при этом основной контекст не разрастается бесконтрольно, workers не конфликтуют друг с другом, сильные модели не тратятся на механическую работу, а системные файлы существующего проекта защищены.

---

# 31. Следующий шаг для нового чата

Не нужно сразу писать skill.

Сначала нужно вместе спроектировать **Codex Autopilot V1**.

Желательный следующий порядок:

```text
1. Проверить актуальную документацию Codex/OpenAI.
2. Ещё раз изучить upstream Autopilot.
3. Составить component map:
   KEEP / MODIFY / REWRITE / DROP / ADD.
4. Спроектировать роли агентов.
5. Спроектировать model-routing policy.
6. Спроектировать context contracts.
7. Спроектировать filesystem/write safety.
8. Спроектировать preflight.
9. Определить V1 scope.
10. Только после этого готовить specification для Astra.
```

Важно сохранять прагматичный подход.

Цель V1 — не создать идеальную универсальную multi-agent platform, а получить **рабочий Codex-native Autopilot для собственных проектов**, сохранив сильные стороны существующей методологии и устранив лишний Claude/bridge слой.

---

## Короткая формула всего проекта

```text
Autopilot methodology
        +
Codex native orchestration
        +
Codex subagents
        +
model/reasoning routing
        +
strict context isolation
        +
write-zone safety
        +
independent review
        =
CODEX AUTOPILOT
```

---

# 32. Durable status: v1.1.0 hardening through Phase D

Актуальное состояние для следующей сессии определяется Git и [`reports/v1.1.0-hardening-progress.md`](../../reports/v1.1.0-hardening-progress.md).

- Ветка: `codex/v1.1.0-hardening`.
- Phase A, Phase B, Phase C и Phase D завершены.
- Phase D implementation commit: `e92fb34` — typed effect lifecycle, applied-effect adoption/finalization, shared immutable `VerifiedCandidateProof` и strong ordinary candidate publication.
- Candidate effect states: `prepared → applied/uncertain/abandoned`, `uncertain → applied/abandoned`, `applied → finalized`. Applied-but-unlinked candidate commit остаётся pinned и получает typed `adopt_applied_effect`; Git повторно не выполняется.
- `candidate` и `preserve-blocked-candidate` используют один finalizer: exact run/ticket/attempt/operation receipt binding, direct parent/base/commit/tree checks, clean checkout и полный tracked/untracked/ignored/rename/type/mode/symlink audit. Receipt, audit и proof сохраняются content-addressed и связываются с attempt/candidate/finalized operation.
- Полный suite: 170 tests in 348.744 s, OK, skipped=1 (документированный opt-in production-checkpoint audit). Focused Phase D + continuation/Wave1/model/v1.0.4 suite: 31/31; dedicated Phase D modules: 11/11.
- v1.0.4 qualification: OK; 40-ticket qualification переведена на 40 real Git commits с полным proof audit и прошла внутри final suite под лимитом `<180s`.
- `py_compile`, contracts/lifecycle JSON parse и `git diff --check`: PASS.
- Live Idea Scout не открывался и не изменялся; production R58 migration остаётся только Phase F.
- Phase E не начата. Следующий шаг в новой сессии — Phase E из master hardening plan. Push не выполнялся.
