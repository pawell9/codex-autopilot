# References — provenance и уровень доверия

Эта директория собирает входные материалы для research/design-этапа `codex-autopilot`.
Материалы не изменялись по содержанию (кроме переименования/распаковки при переносе).

**Состояние corpus на 2026-09-12:** все входные категории из `PROJECT-BRIEF.md` §13
собраны (upstream, evidence Idea Scout V1, официальные источники OpenAI/Codex,
community, handoff). Анализ (KEEP / MODIFY / REWRITE / DROP / ADD) ещё не начат;
`research/` пуст.

## Сводка категорий

| Категория | Путь | Происхождение | Уровень доверия |
|---|---|---|---|
| Проектные решения | `../PROJECT-BRIEF.md` | пользователь | наивысший (намерение) |
| Upstream Autopilot | `../upstream/autopilot/` | `nick-vels/skills@99c7e73` | эталон текущей реализации |
| Evidence реального прогона | `idea-scout-v1/` | read-only выгрузка из Idea Scout V1 | факты прогона |
| Официальные OpenAI/Codex | `official/` | learn.chatgpt.com, developers.openai.com, openai.com, github.com/openai | авторитетно для возможностей Codex (на дату проверки) |
| Community | `community/` | видео + workspace автора видео | гипотезы, требуют проверки |
| Handoff | `handoffs/` | ранний design-документ | контекстный / исторический |

## `../PROJECT-BRIEF.md`

Текущие проектные решения пользователя. Основной источник целей и требований для
`codex-autopilot`. Наивысший уровень доверия — отражает актуальное намерение пользователя
на момент написания брифа.

## `../upstream/autopilot/` (вне `references/`, но часть corpus)

Актуальная папка skill Autopilot из публичного репозитория автора методологии.

- Repository: https://github.com/nick-vels/skills
- Branch: `main`, commit `99c7e73678195cac08080bdd442f0e49a7ccb640` (2026-08-19)
- Путь в репозитории: `skills/autopilot/` → скопирован в `upstream/autopilot/` 2026-09-12
  без изменений (проверено `diff -r`), 21 файл.
- Полный provenance, хэши и список того, что из репозитория не копировалось:
  `../upstream/PROVENANCE.md`.

Уровень доверия: авторитетный источник **текущей upstream-реализации** методологии.
Это не то же самое, что версия skill, использованная в Idea Scout V1
(`idea-scout-v1/autopilot-skill-used/`) — связь между ними ещё не сверялась.

## `idea-scout-v1/`

Read-only evidence bundle реального end-to-end прогона Autopilot на проекте Idea Scout
(`PROJECT-BRIEF.md` §12: версия `v1.0.0`, acceptance commit `c03e78b`, статус
`ACCEPTED V1`). Production-репозиторий Idea Scout не изменялся.

Содержимое:

- `autopilot-skill-used/` — копия skill Autopilot в том виде, в каком он применялся
  в прогоне;
- `agent-rules/` — проектные `AGENTS.md`, `CLAUDE.md`, `.codex/config.toml`,
  `docs/executor.md`;
- `run-artifacts/2026-09-05-idea-scout/` — brief, manifest, spec, interfaces, reference,
  review-log, Astra-ревью архитектуры и плана, handoff'ы волны 4, 17 тикетов;
- `runtime-state/` — `state.js`, `sync.py`, `README.md` из `.autopilot/`;
- `git-log-oneline.txt` — 136 коммитов, верхний — `c03e78b chore: final acceptance V1`.

Уровень доверия: первичные факты о том, как методология отработала на практике.
Отдельного provenance-файла у bundle нет: дата выгрузки и commit исходной копии
skill в bundle не зафиксированы (кроме acceptance commit проекта).

## `official/`

### `official/openai-links.md`

Индекс официальных источников OpenAI/Codex, проверенных 2026-09-12:
subagents и custom agents, skills, AGENTS.md, модели и reasoning effort,
конфигурация, sandbox / permissions / approvals, контекст, long-running work,
resume, review, а также Codex Security. Для каждого источника указаны URL,
что он подтверждает, зачем он нужен аудиту и дата/уровень проверки.
В конце — выявленные расхождения между официальными страницами.

Важно: `developers.openai.com/codex/*` теперь редиректит (308) на
`learn.chatgpt.com/docs/*`.

### `official/snapshots/`

Небольшие дословные snapshot'ы сырого markdown двух быстро меняющихся критичных страниц
(Subagents, Models) с sha256 и датой получения — см. таблицу в конце `openai-links.md`.
Остальные официальные источники намеренно оставлены ссылками.

Уровень доверия: авторитетно для возможностей Codex **на дату проверки**. Документация
не содержит дат обновления и местами противоречит сама себе (reasoning effort, slug
моделей) — такие пункты проверяются в фактическом runtime/preflight.

## `handoffs/codex-autopilot-handoff.md`

Исторический design/context документ (детальный handoff по переходу с
Claude Code + Codex executors на полностью Codex-native оркестрацию).

Уровень доверия: контекстный/исторический. Полезен для понимания эволюции идеи,
мотивации и ранних архитектурных набросков, но зафиксированные в нём решения
(модели, tiers, конкретные названия) явно помечены как незакреплённые и подлежат
проверке/пересмотру на этапе research/design.

## `community/gpt6-astra-video-transcript.txt`

Транскрипт видео о возможностях GPT-6 / Astra / Codex (community-обзор, ~30 концептов).

Уровень доверия: свежий практический/community reference. Ценен как источник гипотез
о современных возможностях Codex (subagents, model/reasoning routing, память,
разрешения, лимиты и т.д.), но это не официальная документация. Технические claims
(названия моделей, точные лимиты, поведение фич) требуют проверки по официальной
документации OpenAI/Codex (`official/openai-links.md`) или по фактическому рантайму
перед тем, как закладываться в архитектуру.

## `community/gpt6-workspace/`

Практический пример рабочего пространства Codex (config.toml, AGENTS.md, .codex/agents,
scripts, rules и т.д.), сопровождавший вышеуказанное видео.

Уровень доверия: practical reference / config example. Полезен как иллюстрация того,
как кто-то настроил Codex-workspace на практике (permissions, guardian, subagents,
memory), но:

- это не официальная документация;
- настройки могут быть специфичны для чужого проекта/предпочтений;
- **не копировать эти настройки автоматически** — любое заимствование (config.toml,
  права доступа, структура агентов) должно быть отдельно проверено на совместимость
  с текущей версией Codex и с требованиями безопасности `codex-autopilot`
  (см. `PROJECT-BRIEF.md`, разделы 9–10).

## Что сюда пока не входит

- `../research/` — результаты research/design-аудита, ещё не подготовлены.
- Материалы `writing-for-agents` (Matt Pocock), упомянутые в `PROJECT-BRIEF.md` §11 и §13 п.8,
  в corpus не сохранены.
