# Official OpenAI references

## Codex Security
https://github.com/openai/codex-security

Official OpenAI security CLI/SDK.

Relevant for future research into:
- security review;
- security-policy generation;
- possible review / acceptance integration;
- bounded workers/subagents in security workflows.

Do not treat Codex Security implementation details as generic Codex orchestration rules unless confirmed by current official Codex documentation.

---

# Codex / OpenAI — индекс официальных источников для design-аудита

**Дата проверки всех источников ниже:** 2026-09-12.
**Только официальные источники OpenAI** (`learn.chatgpt.com`, `developers.openai.com`,
`openai.com`, `github.com/openai`). Community-материалы сюда не входят.

## Как читать этот индекс

- **Домены.** Документация Codex переехала: `https://developers.openai.com/codex/*`
  отвечает `308 Permanent Redirect` на `https://learn.chatgpt.com/docs/*`
  (сайт называется «ChatGPT Learn»). Старые ссылки из handoff/community
  работают только через redirect. Документация API моделей осталась на
  `developers.openai.com/api/docs/*`.
- **Markdown-версия.** К любой странице `learn.chatgpt.com/docs/...` можно добавить
  `.md` — получится сырой markdown. Полный индекс: https://learn.chatgpt.com/llms.txt
  (и https://learn.chatgpt.com/docs/llms.txt).
- **Поверхности.** Страницы общие для ChatGPT Work (web) и Codex (app / CLI / IDE),
  блоки размечены `ContentModeSwitch`. Для `codex-autopilot` релевантны блоки
  `app,cli,ide` (локальный Codex); web-блоки часто описывают иное поведение.
- **Дат обновления на страницах нет.** Единственная временная привязка — дата
  проверки. Maturity-метки (Experimental / Beta / Stable) указаны там, где есть.
- **Уровень проверки.** `raw` — прочитан сырой `.md`; `summary` — содержимое
  получено через пересказ страницы (точные значения стоит перепроверить);
  `link-only` — содержимое не получено.
- **Локальные snapshot'ы** — в `snapshots/` (см. раздел в конце).

---

## 1. Навигация, зрелость фич, версии

### Codex docs index (llms.txt)
- **URL:** https://learn.chatgpt.com/llms.txt
- **Подтверждает:** полный актуальный список страниц документации Codex / ChatGPT Work.
- **Зачем аудиту:** точка входа для повторной проверки; позволяет найти страницы,
  которых нет в этом индексе.
- **Проверено:** 2026-09-12 (raw).

### Feature maturity
- **URL:** https://learn.chatgpt.com/docs/feature-maturity
- **Подтверждает:** значения меток Under development / Experimental / Beta /
  Stable / Deprecated и рекомендации по использованию каждой.
- **Зачем аудиту:** опираться в V1 можно только на Stable, а Beta и Experimental
  (например, permission profiles, experimental context management) — только с fallback.
- **Проверено:** 2026-09-12 (raw).

### What's new (еженедельный дайджест)
- **URL:** https://learn.chatgpt.com/docs/whats-new
- **Подтверждает:** хронологию фич; GPT-6 Astra в Codex — неделя August 31–September 4, 2026;
  упоминания Codex CLI 0.146.0 / 0.147.0.
- **Зачем аудиту:** быстро понять, что изменилось с момента handoff / записи видео.
- **Проверено:** 2026-09-12 (raw, первые разделы). Ссылка на changelog
  (`/docs/changelog.md`) вернула 404; HTML-версия не проверялась.

### openai/codex (исходники и релизы Codex CLI)
- **URL:** https://github.com/openai/codex · релизы: https://github.com/openai/codex/releases
- **Подтверждает:** open-source CLI, app-server и SDK. Последний релиз на дату проверки —
  `rust-v0.154.0` (0.154.0), опубликован 2026-09-09.
- **Зачем аудиту:** минимальная версия для preflight и сверка реального поведения
  (например, инструменты `spawn_agent` и др.) по исходникам, когда документация неполна.
- **Проверено:** 2026-09-12 (GitHub API `releases/latest`).

### Open source (карта официальных репозиториев)
- **URL:** https://learn.chatgpt.com/docs/open-source
- **Подтверждает:** официальные репозитории: `openai/codex`, `openai/codex-security`,
  `openai/skills`, `openai/plugins`, `openai/codex-universal`.
- **Зачем аудиту:** отличить официальные примеры skills и plugins от community.
- **Проверено:** 2026-09-12 (raw).

---

## 2. Subagents, custom agents, делегирование и параллельная работа

### Subagents ★ (snapshot сохранён)
- **URL:** https://learn.chatgpt.com/docs/agent-configuration/subagents
  (redirect со старого https://developers.openai.com/codex/subagents)
- **Подтверждает:**
  - Subagent workflows включены по умолчанию в текущих локальных релизах.
    Локальный Codex делегирует **только** по прямой просьбе или по инструкции
    в `AGENTS.md` / skill (проактивное делегирование описано лишь для Ultra
    в ChatGPT Work).
  - Subagents тратят больше токенов. Рекомендация — параллелить read-heavy
    работу (exploration, tests, triage, summarization) и осторожнее обращаться
    с параллельной записью из-за конфликтов.
  - Обоснование: context pollution / context rot; subagents возвращают **summaries**.
  - Built-in агенты: `default`, `worker`, `explorer`. Custom agents — TOML-файлы в
    `~/.codex/agents/` и `.codex/agents/`, обязательные поля: `name`, `description`,
    `developer_instructions`. Также допустимы любые ключи `config.toml`
    (`model`, `model_reasoning_effort`, `sandbox_mode`, `mcp_servers`,
    `skills.config`). Формат «may evolve».
  - Порядок разрешения model/effort: явное значение при spawn → дефолт из `[agents]`
    → значение родителя. Значение из файла custom agent имеет приоритет.
  - `[agents]`: `enabled`, `max_concurrent_threads_per_session`
    (legacy `max_threads`), `default_subagent_model`,
    `default_subagent_reasoning_effort`, `interrupt_message`.
  - Subagents наследуют sandbox policy и permission mode родителя. `sandbox_mode`
    можно переопределить в файле custom agent, **но** live runtime overrides
    родителя (`/permissions`, `--yolo`) применяются к ребёнку заново,
    даже если файл агента задаёт другое.
  - В non-interactive режиме действие, требующее нового approval, завершается ошибкой,
    и она возвращается родителю.
  - CLI: `/agent` переключает agent threads; approval overlay показывает поток-источник.
- **Зачем аудиту:** главный источник для agent roles, model/reasoning routing,
  context contracts, parallelism policy и write-zone safety. Пункт про runtime
  overrides напрямую влияет на то, можно ли гарантировать read-only reviewer.
- **Не документировано:** глубина вложенности subagents, дефолт
  `max_concurrent_threads_per_session`, формат/схема возвращаемого summary.
- **Проверено:** 2026-09-12 (raw).

### Configuration Reference — multi-agent и связанные ключи
- **URL:** https://learn.chatgpt.com/docs/config-file/config-reference
- **Подтверждает:**
  - `features.multi_agent` включает инструменты `spawn_agent`, `send_input`,
    `resume_agent`, `wait_agent`, `close_agent` (stable; on by default).
  - `agents.<name>.description`, `agents.<name>.config_file` — роли в `config.toml`.
  - `features.goals` — persisted goals и automatic continuation (stable; on by default).
- **Зачем аудиту:** точные названия примитивов оркестрации, на которых можно строить
  dispatch / wait / close воркеров и resume агента.
- **Проверено:** 2026-09-12 (raw, точечные разделы).

### Hooks
- **URL:** https://learn.chatgpt.com/docs/hooks
- **Подтверждает:** события `SessionStart`, `SessionEnd`, `SubagentStart`, `SubagentStop`,
  `PreToolUse`, `PermissionRequest`, `PostToolUse`, `PreCompact`, `PostCompact`,
  `UserPromptSubmit`, `Stop`, `Interrupt`.
  - `SubagentStart` может добавить developer context субагенту.
  - `SubagentStop` получает `agent_transcript_path` и `last_assistant_message`
    и может вернуть `decision: "block"` для ещё одного прохода.
  - Несовпадающие по источнику hooks запускаются параллельно.
  - Non-managed hooks требуют review / trust.
- **Зачем аудиту:** детерминированные точки для валидации return contract, telemetry,
  write-zone guard (PreToolUse) и checkpoint при compaction.
- **Проверено:** 2026-09-12 (raw, точечные разделы).

### Git worktrees
- **URL:** https://learn.chatgpt.com/docs/environments/git-worktrees
- **Подтверждает:** managed / permanent worktrees в desktop app, handoff Local↔Worktree,
  `.worktreeinclude`, ограничения веток, очистка.
- **Зачем аудиту:** механизм изоляции параллельных write-воркеров;
  альтернатива или дополнение к write zones.
- **Проверено:** 2026-09-12 (raw, заголовки и начальные разделы).

---

## 3. Skills, AGENTS.md, customization

### Build skills
- **URL:** https://learn.chatgpt.com/docs/build-skills
- **Подтверждает:**
  - `SKILL.md` с обязательными `name` и `description`; опциональные папки
    `scripts/`, `references/`, `assets/`, а также `agents/openai.yaml`
    (`policy.allow_implicit_invocation`, зависимости MCP).
  - Progressive disclosure: сначала грузятся только name/description
    (бюджет списка ≈2% контекста / ≤8000 символов). Полный `SKILL.md` —
    при выборе skill.
  - Scopes: `$CWD/.agents/skills` … `$REPO_ROOT/.agents/skills` (REPO),
    `$HOME/.agents/skills` (USER), `/etc/codex/skills` (ADMIN), SYSTEM.
    Одноимённые skills не сливаются. Симлинки поддерживаются.
  - Вызов: явный (`$skill`, `/skills`) и неявный (по `description`).
  - Выключение: `[[skills.config]]` с `enabled = false`.
- **Зачем аудиту:** структура и размещение `codex-autopilot`, бюджет always-loaded
  контекста, триггер-description, разбиение на phase-файлы.
- **Проверено:** 2026-09-12 (raw).

### Skills & Plugins
- **URL:** https://learn.chatgpt.com/docs/skills-and-plugins
- **Подтверждает:** когда использовать skill, а когда plugin (распространение,
  bundling skills + MCP).
- **Зачем аудиту:** решение о форме поставки (`codex-autopilot` как skill или как plugin).
- **Проверено:** 2026-09-12 (raw, заголовки).

### Custom instructions with AGENTS.md
- **URL:** https://learn.chatgpt.com/docs/agent-configuration/agents-md
  (redirect с https://developers.openai.com/codex/guides/agents-md)
- **Подтверждает:**
  - Цепочка: global `~/.codex/AGENTS.override.md` | `AGENTS.md`, затем project
    от корня до CWD, по одному файлу на директорию, конкатенация сверху вниз.
  - `project_doc_max_bytes` (32 KiB по умолчанию), `project_doc_fallback_filenames`.
  - Цепочка строится один раз на запуск.
- **Зачем аудиту:** что skill может ожидать от проектного `AGENTS.md`, лимит размера,
  риск конфликта с preserve-by-default для `AGENTS.md` (brief §9).
- **Проверено:** 2026-09-12 (raw).

### Customization overview
- **URL:** https://learn.chatgpt.com/docs/customization/overview
- **Подтверждает:** слои кастомизации — AGENTS.md («keep it small», feedback loop),
  skills, MCP, subagents; зависимость skill от MCP объявляется в `agents/openai.yaml`.
- **Зачем аудиту:** распределение ответственности между AGENTS.md, skill, custom agents.
- **Проверено:** 2026-09-12 (raw).

### Memories
- **URL:** https://learn.chatgpt.com/docs/customization/memories
- **Подтверждает:** локальные memories в `~/.codex/memories/` — сгенерированное состояние,
  обновляется фоново и с задержкой. Документация прямо говорит: обязательные
  правила хранить в `AGENTS.md` / docs, memories — «recall layer, not the only source».
- **Зачем аудиту:** project memory Autopilot должна жить в файлах проекта,
  а не опираться на Codex memories.
- **Проверено:** 2026-09-12 (raw).

### openai/skills
- **URL:** https://github.com/openai/skills
- **Подтверждает:** официальный репозиторий переиспользуемых skills.
- **Зачем аудиту:** эталонные примеры структуры skill от OpenAI.
- **Проверено:** 2026-09-12 (link-only, HTTP 200).

---

## 4. Модели, reasoning effort, скорость и экономика

### Codex Models ★ (snapshot сохранён)
- **URL:** https://learn.chatgpt.com/docs/models
- **Подтверждает:**
  - Рекомендованные модели: `gpt-6-astra`, `gpt-5.6-sol`, `gpt-5.6-terra`,
    `gpt-5.6-luna`. Для app/CLI/IDE ещё `gpt-5.3-codex-spark`
    (research preview, text-only, только ChatGPT Pro).
  - Роли: Astra — самая трудная end-to-end работа; Sol — сложная открытая;
    Terra — повседневная; Luna — ясные повторяемые задачи.
  - «Use the lowest reasoning effort that produces the result you need».
    Max — больше времени на одну задачу; Ultra — использует subagents.
    «Most tasks do not need Max or Ultra».
  - Нет точного соответствия effort между GPT-5.5 и GPT-5.6.
  - `gpt-5.4` и `gpt-5.4-mini` выведены из Codex (ChatGPT sign-in) 2026-08-31;
    `gpt-5.2`, `gpt-5.3-codex` — deprecated.
  - Codex cloud: у Astra/Terra/Luna `false`, у Sol `true`; дефолт cloud-модели не меняется.
  - Experimental context management:
    `features.context_management.experimental_mode = true` —
    только Plus/Pro, по умолчанию выключено.
- **Зачем аудиту:** основа model routing и preflight-проверки доступных моделей.
- **Проверено:** 2026-09-12 (raw).

### Speed (Fast mode, Codex-Spark)
- **URL:** https://learn.chatgpt.com/docs/agent-configuration/speed
- **Подтверждает:** Fast mode даёт 1.5× скорость. Кредиты: 2.5× для GPT-5.6/5.5 и
  GPT-6 Astra, 2× для GPT-5.4. Включение: `/fast`, `service_tier = "fast"`
  + `[features].fast_mode = true`. Codex-Spark — отдельная модель
  со своими лимитами.
- **Зачем аудиту:** экономика лимитов (brief §5) — fast mode не должен
  включаться по умолчанию для воркеров.
- **Проверено:** 2026-09-12 (raw).

### Pricing / usage limits
- **URL:** https://learn.chatgpt.com/docs/pricing
- **Подтверждает:** ChatGPT Work и Codex делят одни лимиты; FAQ «What happens when you hit
  usage limits?», совет переключиться на меньшую модель; учёт Code Review usage.
- **Зачем аудиту:** budget awareness, safe stop при исчерпании лимитов.
- **Проверено:** 2026-09-12 (raw, заголовки и grep; таблицы лимитов не извлекались).

### API Models (обзор)
- **URL:** https://developers.openai.com/api/docs/models
- **Подтверждает:** frontier-модели `gpt-6-astra`, `gpt-5.6-sol`, `gpt-5.6-terra`,
  `gpt-5.6-luna`; `gpt-5.6` — **алиас GPT-5.6 Sol**.
- **Зачем аудиту:** объясняет, почему Codex-доки пишут `gpt-5.6`, а в списке —
  `gpt-5.6-sol`.
- **Проверено:** 2026-09-12 (summary).

### API model pages
- **URLs:**
  - https://developers.openai.com/api/docs/models/gpt-6-astra
  - https://developers.openai.com/api/docs/models/gpt-5.6-sol
  - https://developers.openai.com/api/docs/models/gpt-5.6-terra
  - https://developers.openai.com/api/docs/models/gpt-5.6-luna
- **Подтверждает (по API, не по Codex-подписке):**
  - Контекст у всех четырёх: 1,050,000 токенов, max output 128,000.
    Для Astra max input — 922,000.
  - Reasoning effort: Astra — `low, medium, high, xhigh, max`;
    GPT-5.6 Sol/Terra/Luna — `none, low, medium (default), high, xhigh, max`.
  - Knowledge cutoff: Astra — 2026-04-30; GPT-5.6 — 2026-02-16.
  - Цена за 1M токенов input/output: Astra $10/$50, Sol $4/$20,
    Terra $2/$12, Luna $0.2/$1.2. Для GPT-5.6 при >272K input
    действуют множители.
- **Зачем аудиту:** относительная стоимость и потолки контекста для routing;
  валидные значения effort по моделям.
- **Проверено:** 2026-09-12 (summary — точные числа перепроверить перед фиксацией).

### GPT-6 Astra announcement
- **URL:** https://openai.com/index/gpt-6-astra/
- **Подтверждает:** официальный анонс модели (по поисковой выдаче).
- **Зачем аудиту:** контекст возможностей Astra; первичные технические данные брать
  из страниц docs выше.
- **Проверено:** 2026-09-12 (link-only — прямой запрос вернул HTTP 403).

---

## 5. Конфигурация

### Config basics
- **URL:** https://learn.chatgpt.com/docs/config-file/config-basic
- **Подтверждает:** расположение `config.toml` и порядок приоритета конфигурации.
  На раздел ссылается страница Subagents (`#configuration-precedence`).
- **Зачем аудиту:** предсказуемое слияние user- и project-конфига для preflight.
- **Проверено:** 2026-09-12 (скачан raw, содержимое детально не извлекалось).

### Advanced configuration
- **URL:** https://learn.chatgpt.com/docs/config-file/config-advanced
- **Подтверждает:**
  - Profiles: `--profile name` → `~/.codex/name.config.toml`.
  - Project config `.codex/config.toml`, one-off overrides `-c key=value`,
    project root detection, granular approval policy, named permission profiles.
  - OTel-метрики, в том числе `multi_agent.resume`, `task.compact`, `thread.fork`.
- **Зачем аудиту:** профили под роли (planning / executor / reviewer) и
  наблюдаемость экономики оркестрации.
- **Проверено:** 2026-09-12 (raw, заголовки и точечные разделы).

### Configuration Reference
- **URL:** https://learn.chatgpt.com/docs/config-file/config-reference
- **Подтверждает:**
  - `model`, `review_model`.
  - `model_reasoning_effort`: `minimal | low | medium | high | xhigh`
    (xhigh model-dependent).
  - `plan_mode_reasoning_effort`, `model_reasoning_summary`, `model_verbosity`.
  - `approval_policy`: `on-request | never | { granular }`.
  - `sandbox_mode`: `read-only | workspace-write | danger-full-access`,
    `sandbox_workspace_write.*`, `default_permissions`, `permissions.<name>.*`.
  - `approvals_reviewer`.
  - `project_doc_max_bytes`, `skills.max_context_tokens`, `skills.config`.
  - Флаги `features.*` (`multi_agent`, `goals`, `hooks`, `memories`,
    `network_proxy`, `context_management.experimental_mode`).
  - Compaction: `model_auto_compact_token_limit` (+ `_scope`),
    `compact_prompt`; также `tui.resume_cwd`.
- **Зачем аудиту:** авторитетные названия ключей для preflight / doctor и custom agents.
- **Проверено:** 2026-09-12 (raw, grep по ключам; страница ~112 KB, целиком не копировалась).

### Configuration (обзор)
- **URL:** https://learn.chatgpt.com/docs/configuration
- **Подтверждает:** входная страница раздела конфигурации.
- **Зачем аудиту:** навигация.
- **Проверено:** 2026-09-12 (raw, без детального разбора).

---

## 6. Sandbox, permissions, approvals

### Sandbox
- **URL:** https://learn.chatgpt.com/docs/sandboxing
- **Подтверждает:**
  - Режимы `read-only` / `workspace-write` (default low-friction) / `danger-full-access`.
  - Sandbox и approvals — разные контроли.
  - Реализации: macOS Seatbelt, Linux/WSL2 `bubblewrap`, native Windows sandbox.
  - `writable_roots`.
- **Зачем аудиту:** базовая модель безопасности для ролей воркеров.
- **Проверено:** 2026-09-12 (raw).

### Agent approvals & security
- **URL:** https://learn.chatgpt.com/docs/agent-approvals-security
- **Подтверждает:**
  - Политика `untrusted` **retired**. Пресеты: Auto
    (`workspace-write` + `on-request`), Read-only, Full access.
  - Granular approval policy.
  - **Protected paths в `workspace-write`: `.git`, `.agents`, `.codex` — read-only
    рекурсивно.**
  - Сеть по умолчанию выключена; `network_proxy` с доменными правилами.
  - `approvals_reviewer = "auto_review"`; OTel; managed configuration.
- **Зачем аудиту:** write-zone safety и ownership (brief §9). Защита `.agents` / `.codex`
  на уровне sandbox — фактор для места хранения skill и state
  (`.autopilot/**` не защищён).
- **Проверено:** 2026-09-12 (raw, точечные разделы).

### Permissions (permission profiles) — Beta
- **URL:** https://learn.chatgpt.com/docs/permissions
- **Подтверждает:**
  - Именованные профили `[permissions.<name>]` с правилами filesystem
    `read` / `write` / `deny` (включая globs) и network.
  - **Не комбинируются** с `sandbox_mode` / `sandbox_workspace_write`:
    если задан `sandbox_mode`, используются старые настройки.
  - Доменные правила работают только при `features.network_proxy = true`.
  - Профиль `:workspace` оставляет `.codex/` и `.git/` read-only.
- **Зачем аудиту:** кандидат на детерминированную запись только в разрешённые зоны.
  Beta, и per-agent профили в документации не описаны.
- **Проверено:** 2026-09-12 (raw, точечные разделы).

### Permission modes
- **URL:** https://learn.chatgpt.com/docs/permission-modes
- **Подтверждает:** UI-режимы Ask for approval / Approve for me (Auto-review) / Full access;
  смена reviewer не расширяет sandbox; `/permissions` в CLI.
- **Зачем аудиту:** терминология для инструкций пользователю в preflight.
- **Проверено:** 2026-09-12 (raw).

### Auto-review
- **URL:** https://learn.chatgpt.com/docs/sandboxing/auto-review
- **Подтверждает:** отдельный reviewer-агент оценивает только запросы на выход за
  sandbox; работает лишь при интерактивных approvals (не при `never`);
  «not a deterministic security guarantee».
- **Зачем аудиту:** автономные прогоны без ручных approvals при сохранении границ.
- **Проверено:** 2026-09-12 (raw, точечные разделы).

### Rules (execpolicy)
- **URL:** https://learn.chatgpt.com/docs/agent-configuration/rules
- **Подтверждает:** файлы `.rules` для разрешения/запрета команд, разбор compound-команд,
  тестирование правил.
- **Зачем аудиту:** запрет деструктивных команд как «не incidental behaviour» (brief §9).
- **Проверено:** 2026-09-12 (raw, заголовки).

---

## 7. Контекст, long-running work, resume и checkpoints

### Long-running work (Goal mode)
- **URL:** https://learn.chatgpt.com/docs/long-running-work
- **Подтверждает:**
  - `/goal` в app / CLI / IDE: текст goal — и первый prompt, и критерий завершения;
    pause / resume / edit / clear.
  - Сначала `/plan` для неясных задач.
  - Goal не расширяет sandbox и approvals.
  - Параллельные chats — через worktrees, не менять одни файлы.
- **Зачем аудиту:** нативная альтернатива / опора для «continue autopilot»
  и completion criteria.
- **Проверено:** 2026-09-12 (raw).

### CLI slash commands и команды
- **URL:** https://learn.chatgpt.com/docs/developer-commands?surface=cli
- **Подтверждает:**
  - `/agent` (`/subagents`), `/compact` (замена ранних ходов summary),
    `/plan`, `/goal`, `/fork`, `/resume`, `/review`, `/status`
    (модель, approval policy, writable roots, остаток контекста).
  - `codex resume` (`--last`, `--all`), `codex fork`.
- **Зачем аудиту:** checkpoint / resume и контроль контекста доступными
  пользователю средствами.
- **Проверено:** 2026-09-12 (raw, grep).

### Non-interactive mode (`codex exec`)
- **URL:** https://learn.chatgpt.com/docs/non-interactive-mode
- **Подтверждает:**
  - `codex exec` по умолчанию в read-only sandbox.
  - `--output-schema` + `-o`: финальный ответ по JSON Schema.
  - `codex exec resume --last` / `<SESSION_ID>`.
  - Нужен Git-репозиторий (`--skip-git-repo-check`); `--full-auto` deprecated.
  - `--ignore-user-config`, `--ignore-rules`.
- **Зачем аудиту:** структурированные return contracts, изолированные запуски
  для dry-run и тестов skill.
- **Проверено:** 2026-09-12 (raw, точечные разделы).

### Codex App Server
- **URL:** https://learn.chatgpt.com/docs/app-server
- **Подтверждает:**
  - `thread/start`, `thread/resume`, `thread/fork`; thread goals.
  - Compaction треда, rollback последних ходов, steer / interrupt хода,
    запуск skill, review.
  - Часть API за `experimentalApi`; WebSocket transport experimental.
- **Зачем аудиту:** описывает примитивы сессий, если в будущем понадобится
  внешний оркестратор или telemetry. Для V1 skill, скорее всего, справочно.
- **Проверено:** 2026-09-12 (raw, заголовки и grep).

### Codex SDK
- **URL:** https://learn.chatgpt.com/docs/codex-sdk
- **Подтверждает:** TypeScript / Python SDK для программного управления Codex;
  `codex mcp-server` удалён в пользу app-server.
- **Зачем аудиту:** автоматизированные тестовые прогоны skill (brief §15).
- **Проверено:** 2026-09-12 (raw, начало).

### Best practices (гайд)
- **URL:** https://learn.chatgpt.com/guides/best-practices
  (redirect с https://developers.openai.com/codex/learn/best-practices)
- **Подтверждает:**
  - Prompt = goal / context / constraints / done-when.
  - Plan перед сложными задачами; короткий и точный `AGENTS.md`.
  - `/compact`; «one chat per coherent unit of work»; worktrees для долгих задач.
  - Subagents для exploration / tests / triage; повторяющийся workflow → skill.
  - Проверка через tests / lint / `/review`.
- **Зачем аудиту:** официальная позиция OpenAI по дисциплине работы; сверка с
  instruction design (brief §11).
- **Проверено:** 2026-09-12 (summary; `.md`-версия вернула 404).

### Scheduled tasks (Automations)
- **URL:** https://learn.chatgpt.com/docs/automations
- **Подтверждает:** расписания и триггеры от событий, worktree cleanup,
  модель прав scheduled tasks, пример связки со skill.
- **Зачем аудиту:** справочно — вне ядра V1, но может заменить внешние heartbeat-скрипты.
- **Проверено:** 2026-09-12 (raw, заголовки).

---

## 8. Review patterns

### Code review
- **URL:** https://learn.chatgpt.com/docs/code-review
- **Подтверждает:**
  - `/review` запускает dedicated reviewer, который не меняет working tree.
  - Scopes: base branch, uncommitted, commit, custom instructions.
  - `review_model` задаёт модель ревью.
  - Detached review chat (app / IDE).
  - При применении fixes действуют обычные sandbox и approvals.
- **Зачем аудиту:** нативный reviewer lifecycle и возможность отдельной модели
  для review gates.
- **Проверено:** 2026-09-12 (raw).

### Subagents — паттерн параллельного ревью
- **URL:** https://learn.chatgpt.com/docs/agent-configuration/subagents
- **Подтверждает:**
  - Официальные примеры: «one agent per point» (security / quality / bugs /
    race / flakiness / maintainability).
  - Набор `pr_explorer` / `reviewer` / `docs_researcher` с `sandbox_mode = "read-only"`
    и `model_reasoning_effort = "high"` для reviewer.
- **Зачем аудиту:** опорный официальный шаблон multi-axis review.
- **Проверено:** 2026-09-12 (raw).

### Prompting
- **URL:** https://learn.chatgpt.com/docs/prompting
- **Подтверждает:** раздел «Prompting Codex» — explain / fix / test / refactor,
  local code review, GitHub PR review с шагами и verification;
  steering и queuing; `/plan` → `/goal`.
- **Зачем аудиту:** официальные формулировки prompt-паттернов для воркеров и ревьюеров.
- **Проверено:** 2026-09-12 (raw, заголовки и точечные разделы).

### Codex Security docs
- **URL:** https://learn.chatgpt.com/docs/security (в том числе `/docs/security/security-review`)
- **Подтверждает:** текущая официальная документация Codex Security
  (дополняет секцию про `openai/codex-security` выше).
- **Зачем аудиту:** опциональный security review gate.
- **Проверено:** 2026-09-12 (link-only, присутствует в llms.txt).

---

## Выявленные расхождения в официальных источниках (для проверки в runtime)

1. **Словарь reasoning effort не согласован:**
   - config reference: `minimal|low|medium|high|xhigh`;
   - страница Subagents: `low|medium|high|xhigh|max|ultra`;
   - API model pages: `none|low|medium|high|xhigh|max` (у Astra без `none`);
   - UI: Light / Medium / High / Extra High / Max / Ultra.

   Ultra описан как режим с subagents, а не только уровень effort.
   Валидные значения нужно проверять в preflight, а не хардкодить.
2. **Slug модели:** Codex-доки используют `gpt-5.6` (алиас Sol по API docs), список
   моделей — `gpt-5.6-sol`. Пример в config reference всё ещё `gpt-5.5`.
   Примеры custom agents используют `gpt-5.3-codex-spark` (Pro-only research preview).
3. **`gpt-6-astra`** есть в Models и What's new, но не в рекомендациях страницы
   Subagents. Доступность зависит от rollout и плана; в Codex cloud — нет.
4. **Custom agent `sandbox_mode` не гарантирует read-only**, если родитель получил
   live override (`--yolo`, `/permissions`).
5. **Permission profiles (Beta)** не комбинируются с `sandbox_mode`; per-agent профили
   не описаны.
6. Не документированы: максимальная глубина вложенности subagents, дефолтный лимит
   параллельных потоков, схема summary от subagent.

---

## Локальные snapshot'ы (`references/official/snapshots/`)

Сохранены только небольшие критичные страницы, которые быстро меняются и содержат
расхождения, важные для routing / roles. Файлы — **сырой markdown без изменений**
(`<страница>.md`, как отдаёт сайт).

| Файл | Источник | Размер | sha256 | Получен |
|---|---|---|---|---|
| `snapshots/2026-09-12-codex-subagents.md` | https://learn.chatgpt.com/docs/agent-configuration/subagents.md | 22 084 B | `578375343fcbb4bfac2121fbc2bc1ef9839b306c98e49e0472310ef6e179f5a6` | 2026-09-12 |
| `snapshots/2026-09-12-codex-models.md` | https://learn.chatgpt.com/docs/models.md | 19 007 B | `f4ffe196ccff81a40e1ff1f80d97ddd0c9523bb01b1716f1bd5a8aa4836bda23` | 2026-09-12 |

Остальные источники оставлены ссылками: при аудите перечитывать актуальную версию
(`URL + .md`).
