window.STATE =
{
  "slug": "idea-scout",
  "dir": "2026-09-05-idea-scout",
  "title": "Парсер идей с подтверждёнными метриками + дашборд",
  "mode": "manual",
  "depth": "deep",
  "polish": null,
  "tier": "T3",
  "briefFile": "2026-09-05-brief.md",
  "memoryFile": "AGENTS.md",
  "skillDir": "<USER_HOME>/.agents/skills/autopilot",
  "startedAt": "2026-09-05T20:53:01+03:00",
  "updatedAt": "2026-09-11T15:30:00+03:00",
  "finishedAt": "2026-09-11T15:30:00+03:00",
  "stages": [
    {
      "id": "preflight",
      "status": "done",
      "startedAt": "2026-09-05T20:53:01+03:00",
      "finishedAt": "2026-09-05T20:53:30+03:00"
    },
    {
      "id": "manifest",
      "status": "done",
      "startedAt": "2026-09-05T20:53:37+03:00",
      "finishedAt": "2026-09-05T20:54:52+03:00"
    },
    {
      "id": "briefing",
      "status": "done",
      "startedAt": "2026-09-05T20:54:52+03:00",
      "finishedAt": "2026-09-05T22:12:40+03:00"
    },
    {
      "id": "spec",
      "status": "done",
      "startedAt": "2026-09-05T22:12:40+03:00",
      "finishedAt": "2026-09-06T00:22:29+03:00"
    },
    {
      "id": "plan",
      "status": "done",
      "startedAt": "2026-09-06T00:22:29+03:00",
      "note": "15 тасков, 7 волн, ярус T3 · утверждён пользователем",
      "finishedAt": "2026-09-06T01:18:00+03:00"
    },
    {
      "id": "build",
      "status": "done",
      "startedAt": "2026-09-06T01:32:36+03:00",
      "finishedAt": "2026-09-09T02:20:00+03:00",
      "note": "Сдано 17 из 17, полностью закрыто включая pytest -m real. Таск 17 (последний, волна 7): маршрут x_apify через Apify (D43–D54), три легитимных BLOCKED исполнителя подряд на контрактный долг D44 закрыты точечными правками (D55–D57), эскалация не потребовалась. При подготовке реального прогона найден и исправлен реальный дефект D58 (Store.migrate() падал на непустой базе — не контрактный долг, обычный цикл Codex → review). Малый реальный сбор x_apify пройден 2026-09-09: 1 passed, реальный расход $0.000122 при резерве $0.00075 — docs/operations.md. pytest -q: 464 passed (два падения на этой машине — активный APIFY_TOKEN в окружении и macOS-команда open, не связаны с кодом задачи, воспроизводимо исчезают вне сессии)."
    },
    {
      "id": "review",
      "status": "done",
      "startedAt": "2026-09-10T16:20:23+03:00",
      "finishedAt": "2026-09-11T14:57:46+03:00",
      "note": "FINAL CODE REVIEW V1 завершён: 19 дедуплицированных root findings закрыты, D59–D62 реализованы, independent targeted re-review чист. pytest: 516 passed, 12 deselected; ruff, format, JS syntax, pip check и read-only browser smoke зелёные. QA/evidence сохранены. Acceptance намеренно не запускался; R29 остаётся для отдельного acceptance-чата."
    },
    {
      "id": "final",
      "status": "done",
      "startedAt": "2026-09-11T15:00:00+03:00",
      "finishedAt": "2026-09-11T15:30:00+03:00",
      "note": "Final acceptance V1 независимым ревьюером на HEAD 09ab69c. Единственная незакрытая позиция — R29 (in-ticket): закрыта живой проверкой claude -p / codex exec / opencode run на реально сгенерированном scaffold-проекте, все три CLI верно прочитали AGENTS.md/CLAUDE.md. Остальные 46 требований приняты по существующему evidence + точечный live-смок дашборда (config.qa-dashboard.toml): список идей, карточка, источники, атрибуция, статус источников — все живые. pytest -q повторно: 516 passed, 12 deselected. Новых дефектов не найдено. Verdict: ACCEPTED V1."
    }
  ],
  "requirements": {
    "total": 47,
    "done": 45,
    "inTicket": 0,
    "inSpec": 0,
    "placeholder": 0,
    "deferred": 1,
    "dropped": 1
  },
  "blind": [],
  "tickets": [
    {
      "id": "01",
      "title": "Каркас: конфиг, база, CLI",
      "requirements": [
        "R15",
        "R21",
        "R21.2",
        "R32i"
      ],
      "blockedBy": [],
      "wave": 1,
      "zone": [
        "pyproject.toml",
        "src/idea_scout/types.py",
        "src/idea_scout/config.py",
        "src/idea_scout/store/",
        "migrations/",
        "src/idea_scout/cli.py",
        "src/idea_scout/commands/",
        ".env.example",
        "tests/conftest.py"
      ],
      "status": "done",
      "retries": 0,
      "repairs": 2,
      "handoffs": 0,
      "startedAt": "2026-09-06T01:32:36+03:00",
      "finishedAt": "2026-09-06T02:03:45+03:00",
      "note": "123 теста · 2 дозапроса · контракт store/cli воплощён дословно"
    },
    {
      "id": "02",
      "title": "Паспорта восьми источников",
      "requirements": [
        "R10",
        "R37i",
        "G09"
      ],
      "blockedBy": [],
      "wave": 1,
      "zone": [
        "docs/sources/",
        "tests/fixtures/"
      ],
      "status": "done",
      "retries": 0,
      "repairs": 1,
      "handoffs": 0,
      "startedAt": "2026-09-06T01:32:36+03:00",
      "finishedAt": "2026-09-06T01:59:34+03:00",
      "note": "8 паспортов, 20 фикстур · разрешён 1 из 8 · ревью чисто, 1 дозапрос"
    },
    {
      "id": "03",
      "title": "Доказательства метрик",
      "requirements": [
        "R05",
        "R05.1",
        "R05.2",
        "R05.3",
        "R05.4",
        "R06",
        "R07",
        "R35i",
        "R35i.1"
      ],
      "blockedBy": [
        "01"
      ],
      "wave": 2,
      "zone": [
        "src/idea_scout/evidence/",
        "migrations/002_evidence.sql",
        "src/idea_scout/types.py (дописывание)",
        "src/idea_scout/store/store.py (дописывание)",
        "src/idea_scout/config.py (дописывание ключа)"
      ],
      "status": "done",
      "retries": 0,
      "repairs": 4,
      "handoffs": 0,
      "note": "исполнитель Codex · 140 тестов · 3 возврата BLOCKED по дефектам контракта (D05-D07), 2 круга ревью",
      "startedAt": "2026-09-06T03:56:59+03:00",
      "finishedAt": "2026-09-06T04:51:11+03:00"
    },
    {
      "id": "04",
      "title": "Идентичность и дедупликация",
      "requirements": [
        "R34i",
        "R34i.1",
        "R34i.2",
        "R32i.1"
      ],
      "blockedBy": [
        "01"
      ],
      "wave": 2,
      "zone": [
        "src/idea_scout/identity/",
        "src/idea_scout/store/store.py (только known_identities, merge_ideas, unmerge)"
      ],
      "status": "done",
      "retries": 0,
      "repairs": 5,
      "handoffs": 0,
      "startedAt": "2026-09-06T14:20:00+03:00",
      "finishedAt": "2026-09-06T15:52:00+03:00",
      "note": "исполнитель Codex, слито в main · шесть кругов до кода: 1-2 неполная зона (D08), 3 инфраструктура (не круг ремонта), 4 отсутствие item в resolve (D09), 5 отсутствие raw_id в mentions (D10). Круг 6: код готов. Оба ревью: без блокирующих по спеке/манифесту кроме одной — тестов не было вообще; дозапрос (1 из 2 разрешённых) добавил 9 тестов, закрыл находку. Слито merge-коммитом, 155 тестов и ruff чисты на main. Неблокирующие находки (домен только косметика в reason, снимок отката закодирован в текстовом поле merge_log.reason, human_status не используется в resolve) — в concerns"
    },
    {
      "id": "05",
      "title": "Очередь работ и бюджет",
      "requirements": [
        "R09",
        "R09.1",
        "R09.2",
        "R09.3",
        "R09.4",
        "R09.5",
        "R30.1"
      ],
      "blockedBy": [
        "01"
      ],
      "wave": 2,
      "zone": [
        "src/idea_scout/queue/",
        "src/idea_scout/budget/",
        "migrations/003_budget.sql",
        "src/idea_scout/store/store.py (только save_reservation, update_reservation, open_reservations, spend_summary; точечно complete_job/claim_job под повторы)",
        "src/idea_scout/config.py (дописывание budget.monthly_cap_usd, D07)"
      ],
      "status": "done",
      "retries": 0,
      "repairs": 2,
      "handoffs": 0,
      "startedAt": "2026-09-06T14:20:00+03:00",
      "finishedAt": "2026-09-06T15:45:00+03:00",
      "note": "исполнитель Codex, слито в main · заход 1 инфраструктура (не круг ремонта), заход 2 неполная зона (store.py), заход 3 неполная зона (config.py, D07) — исправлено. Заход 4: код готов, оба ревью без блокирующих находок. Слито merge-коммитом, 146 тестов и ruff чисты на main. Git commit сделан оркестратором вручную (sandbox-лимит на index.lock) · поправка 2026-09-06: основание бюджета сменилось, протокол резерва сохранён, миграция 003_budget.sql · неблокирующие находки — в concerns"
    },
    {
      "id": "06",
      "title": "Цепочка LLM-провайдеров с изоляцией",
      "requirements": [
        "R22",
        "R22.1",
        "R22.2",
        "R22.3",
        "R22.4",
        "R29",
        "R30",
        "R30.2",
        "G03",
        "A01"
      ],
      "blockedBy": [
        "01"
      ],
      "wave": 2,
      "zone": [
        "src/idea_scout/llm/",
        "src/idea_scout/config.py (дописывание llm.provider_order/llm.timeout_s, D07)"
      ],
      "status": "done",
      "retries": 0,
      "repairs": 2,
      "handoffs": 0,
      "startedAt": "2026-09-06T14:20:00+03:00",
      "finishedAt": "2026-09-06T16:10:00+03:00",
      "note": "исполнитель Codex, слито в main · заход 1 BLOCKED по вине инфраструктуры (не круг ремонта). Заход 2: код готов, оба ревью — блокирует только отсутствие тестов pytest -m real. Дозапрос 1/2 добавил 4 живых теста; один из них, прогнанный оркестратором вживую (Codex здесь авторизован), поймал настоящий баг: codex exec --output-schema требует additionalProperties:false в каждом объекте схемы, иначе invalid_json_schema на каждом вызове. Дозапрос 2/2 исправил это и устаревший --enable web_search_request — подтверждено живым прогоном pytest -m real (сначала красный на баге, потом зелёный после фикса). Слито merge-коммитом, 172 теста и ruff чисты на main. R30 сдан частично — переключение агентов работает для research, не для evaluate (D11). Неблокирующие находки ревью — в concerns"
    },
    {
      "id": "07",
      "title": "Вертикальный срез: протокол источников, Hacker News, сбор с сохранностью",
      "requirements": [
        "R04",
        "R15",
        "R21",
        "R21.1",
        "G01",
        "A02"
      ],
      "blockedBy": [
        "01",
        "02",
        "03",
        "04",
        "05"
      ],
      "wave": 3,
      "zone": [
        "src/idea_scout/sources/",
        "src/idea_scout/pipeline/",
        "src/idea_scout/commands/collect.py",
        "src/idea_scout/commands/reprocess.py",
        "src/idea_scout/handlers/",
        "migrations/004_sources.sql",
        "src/idea_scout/types.py (только четыре поля RawItem)",
        "src/idea_scout/store/store.py (только save_policy, policy_for, stale_policies, set_prefilter и новые колонки в save_raw)",
        "src/idea_scout/config.py (только дописывание четырёх ключей sources.*)",
        "src/idea_scout/cli.py (ровно одна правка: build_context заполняет llm_chain, D13)",
        "tests/"
      ],
      "status": "done",
      "retries": 0,
      "repairs": 4,
      "handoffs": 1,
      "note": "сдан. BLOCKED по дефекту контракта (D14) до первой строки кода. Пять кругов, подъём на Sol High: один класс дефекта — курсор уходит вперёд, непрочитанное остаётся позади, прогон рапортует успех — воспроизвёлся в шести обличьях. Ловили живой сбор, прямые вызовы по краям и два независимых ревьюера, не тесты. Итог: окно 30 дней вычитывается целиком, 5784 уникальных элемента против 301 на первом круге. Контракт доведён до D16, паспорт HN поправлен шестью пунктами. Долг вынесен в тикеты 09, 12, 15",
      "startedAt": "2026-09-06T18:05:00+03:00",
      "finishedAt": "2026-09-06T20:15:00+03:00"
    },
    {
      "id": "08",
      "title": "Оценка: оси, рубрики, уровень, темы, блокеры",
      "requirements": [
        "R01",
        "R01.1",
        "R02",
        "R03",
        "R08",
        "R11",
        "R11.1",
        "R11.2",
        "R19",
        "R19.1",
        "R19.2",
        "R20",
        "R20.1",
        "R20.2",
        "R22",
        "R23",
        "G05",
        "G06",
        "G08"
      ],
      "blockedBy": [
        "05",
        "06",
        "07"
      ],
      "wave": 4,
      "zone": [
        "src/idea_scout/scoring/",
        "config/profile.md",
        "config/rubric.yml",
        "src/idea_scout/handlers/score.py",
        "src/idea_scout/commands/rescore.py",
        "tests/quality/",
        "migrations/006_scoring.sql",
        "src/idea_scout/store/store.py (только save_score, latest_score, фильтры level/theme в list_ideas и _preview, поле score в get_idea)",
        "src/idea_scout/config.py (только дописывание scoring.unreviewed_daily_n, D07)",
        "tests/test_store.py (только: убрать level/theme из test_unsupported_filter_fields_refuse_loudly и latest_score из NOT_IMPLEMENTED_YET — устарели после реализации T08)"
      ],
      "status": "done",
      "retries": 0,
      "repairs": 2,
      "handoffs": 0,
      "startedAt": "2026-09-07T04:20:00+03:00",
      "finishedAt": "2026-09-07T05:10:00+03:00",
      "note": "СДАН и слит в main (bc375c1). Исполнитель — Codex (Terra High), одна сессия целиком, оба круга ремонта решены с первого захода. До старта дополнена зона (store.py/migrations/config.py + точечно tests/test_store.py — пробелы нарезки оркестратора, не исполнителя, кругами ремонта не считаются). Круг 1: оркестратор поймал чтением диффа настоящий дефект до отправки на ревью — compute_level (публичная, её зовёт rescore.py) хардкодила пороги 7.5/5.5, а приватная _level_with_rubric (только score()) честно читала rubric.yml; правка порогов в config/rubric.yml молча не долетала бы до rescore. Сведено к одной функции + тест-мутация, доказывающая llm.calls==0 при смене порога. Круг 2: двойное ревью (review-manifest-spec, review-craft) независимо сошлось на одной находке — 20 размеченных случаев в tests/quality/ различались только homepage/currency/profile, метки категорий (старый кейс, дубли, скриншот, нет метрик) не были подкреплены содержимым; плюс handlers/score.py был не покрыт ни одним тестом. Ни одна находка не была BLOCKING по вердикту ревью, обе отправлены решением оркестратора как реальные пробелы приёмки. 360 тестов и ruff чисты на main. Требования R01, R02, R03, R08, R11, R19, R20, R22 (совместно с T06, сдан частично по D11), R23 закрыты; G06 — механизм сдан, содержимое профиля решением пользователя остаётся заглушкой [ЗАПОЛНИ]."
    },
    {
      "id": "09",
      "title": "Источники MVP: Product Hunt Atom, GitHub, Stack Exchange, RSS",
      "requirements": [
        "R10",
        "R37i"
      ],
      "blockedBy": [
        "07",
        "16"
      ],
      "wave": 4,
      "zone": [
        "src/idea_scout/sources/api/",
        "src/idea_scout/sources/feeds/",
        "config/feeds.yml",
        "src/idea_scout/sources/hackernews.py (только долг из таска 07: комментарии треда, квота не кратна странице, эскалация потока без прогресса)",
        "src/idea_scout/config.py (только дописывание своих ключей)",
        "tests/test_sources_mvp.py и новые файлы фикстур своих источников"
      ],
      "status": "done",
      "retries": 0,
      "repairs": 2,
      "handoffs": 0,
      "note": "СДАН и слит в main (775edb5). Исполнитель — Claude subagent, два круга ремонта. 289 тестов, ruff чист, живой прогон 6 passed / 2 skipped. Оба ревьюера: BLOCKING нет. Круг 1 закрыл две критические находки (SE терял 40 % окна с исходом ok; SE и GitHub клали в SQLite полный ответ площадки). Круг 2 вычистил класс «курсор выше непрочитанного» из трёх оставшихся мест и свёл прогресс в общего стража window_progress. Три правки внесены оркестратором по дефектам паспорта, кругами ремонта не считаются: D34 (у удалённого автора SE профиля нет — запись теряла атрибуцию целиком, поймано живым прогоном при 286 зелёных офлайн, одна запись из 289), безусловное чтение backoff (каждый ранний выход из цикла уносил объявленный срок повтора) и D35. Долг по стражам закрыт 2026-09-07: девять мутаций, все девять краснеют; заведён tests/test_window.py. Реализация при этом не менялась — не хватало доказательства, а не поведения.",
      "startedAt": "2026-09-06T21:35:00+03:00",
      "finishedAt": "2026-09-07T03:10:00+03:00"
    },
    {
      "id": "10",
      "title": "Граница обнаружения и политика источников",
      "requirements": [
        "R10",
        "R04",
        "D04"
      ],
      "blockedBy": [
        "05",
        "07",
        "16"
      ],
      "wave": 4,
      "zone": [
        "src/idea_scout/discovery/",
        "migrations/005_discovery.sql",
        "src/idea_scout/store/store.py (только save_discovery_run)",
        "src/idea_scout/config.py (только дописывание discovery.provider)",
        "tests/test_discovery.py и tests/fixtures/discovery/"
      ],
      "status": "done",
      "retries": 0,
      "repairs": 3,
      "handoffs": 0,
      "note": "СДАН и слит в main (b622c12). Круги 1–2 — Codex Terra High, круг 3 — Sol High свежей сессией по правилу эскалации, плюс дозапрос в ту же сессию. 253 теста, ruff чист. Оба ревьюера: BLOCKING нет. Живой прогон обнаружения невозможен: ключа Tavily нет, тест пропускается. Контракт по таску доведён до D33; пять из шести находок круга 2 и одна из двух круга 3 оказались пробелами контракта, а не промахами исполнителя. Блокирующая находка финального ревью была моей: config.py со снятием freshness_days не попал в коммит, прогон был зелёным по рабочей копии — найдено сверкой коммита с копией, а не прогоном.",
      "startedAt": "2026-09-06T21:35:00+03:00",
      "finishedAt": "2026-09-07T03:15:00+03:00"
    },
    {
      "id": "11",
      "title": "Досье: аналоги в СНГ",
      "requirements": [
        "R12",
        "R12.1",
        "R12.2",
        "R12.3",
        "R12.4",
        "G02"
      ],
      "blockedBy": [
        "06",
        "08"
      ],
      "wave": 5,
      "zone": [
        "src/idea_scout/dossier/",
        "src/idea_scout/handlers/dossier.py",
        "src/idea_scout/store/store.py (save_research, latest_research; точечно одна строка в get_idea())",
        "src/idea_scout/config.py (дописывание dossier.*, D07)",
        "tests/test_store.py (только: убрать latest_research из NOT_IMPLEMENTED_YET)"
      ],
      "status": "done",
      "retries": 0,
      "repairs": 1,
      "handoffs": 0,
      "startedAt": "2026-09-07T05:35:00+03:00",
      "finishedAt": "2026-09-07T06:05:00+03:00",
      "note": "СДАН и слит в main. Исполнитель — свой Claude-субагент, один круг дозапроса (get_idea().research + чистка устаревшего NOT_IMPLEMENTED_YET, оба пункта нашёл сам исполнитель). 397 тестов, ruff чист. Оба ревьюера: BLOCKING нет. Ремесленное ревью — 2 находки, не блокирующие (в concerns): select_finalists не постранично обходит list_ideas при >1000 идей в статусе not_checked; сериализация MetricClaim в JSON дублирует список полей, уже описанный в _claim."
    },
    {
      "id": "12",
      "title": "Дашборд: список, превью, досье, фильтры",
      "requirements": [
        "R08",
        "R12.5",
        "R14",
        "R16",
        "R17",
        "R18",
        "R38i",
        "R38i.1",
        "G01",
        "G04",
        "G04.1",
        "G05",
        "G07",
        "A02"
      ],
      "blockedBy": [
        "01",
        "08"
      ],
      "wave": 5,
      "zone": [
        "src/idea_scout/web/",
        "src/idea_scout/commands/serve.py",
        "src/idea_scout/store/store.py (source_usefulness — D36; ветка trust_level в list_ideas — D37; raw_items_for и ветки в _preview/get_idea — D39)",
        "src/idea_scout/types.py (IdeaFilter.trust_level — D37; IdeaPreview.market/case_date/blocker_count/primary_source_url и IdeaDetail.sources — D39)"
      ],
      "status": "done",
      "retries": 0,
      "repairs": 2,
      "handoffs": 0,
      "startedAt": "2026-09-07T05:35:00+03:00",
      "finishedAt": "2026-09-07T07:20:00+03:00",
      "note": "СДАН и слит в main. Исполнитель — Codex (Terra High), 4 захода. Заход 1: BLOCKED правильно (контракт не нёс read-model полей, D39). Заход 2: код готов, но без тестов — 1 круг ремонта по вине реализации. Заходы 3-4: оркестратор сам нашёл контрактные пробелы чтением диффа до ревью — сортировка по скору/дате (D40), умолчания видимости scope:team/архив и отдельная очередь отставания оценки queue_lag (D41); оба не считаются кругами ремонта. Оба ревьюера: BLOCKING нет, 4 некритичные находки в concerns (сводка сигналов одной фразой, двойной вызов raw_items_for, хрупкий _PAGE.replace, регистр схемы в _safe_url). 427 тестов, ruff чист."
    },
    {
      "id": "13",
      "title": "Дашборд: статусы, действия, защита запросов, клавиатура",
      "requirements": [
        "R12.4",
        "R24",
        "R25",
        "R32i",
        "G03.1",
        "G08",
        "A03"
      ],
      "blockedBy": [
        "11",
        "12",
        "14"
      ],
      "wave": 6,
      "zone": [
        "src/idea_scout/web/",
        "src/idea_scout/web/static/",
        "src/idea_scout/commands/serve.py (только одна строка, D42)",
        "tests/ (правка test_web.py под новую сигнатуру create_app, плюс новые файлы)"
      ],
      "status": "done",
      "retries": 0,
      "repairs": 0,
      "handoffs": 0,
      "startedAt": "2026-09-07T08:10:00+03:00",
      "finishedAt": "2026-09-08T01:55:00+03:00",
      "note": "СДАН и слит в main (проверить хеш после слияния). Исполнитель — Codex (Terra High). Заход 1: BLOCKED верно — зона не называла tests/, а существующий test_web.py звал create_app(store) устаревшей сигнатурой (пробел нарезки, не круг ремонта). Заходы 2-3: два инфраструктурных сбоя оркестратора — забыт флаг --write (сессия ушла в read-only), затем отсутствовал .venv в свежей worktree; ни один не круг ремонта, код не терялся. Заход 4: код готов, тесты и ruff чисты. Оркестратор сам поймал чтением диффа до ревью реальный дефект: review=top брал портацию из unreviewed_top(n), но гидратировал превью вторым вызовом list_ideas с size=n и умолчанием archive_order — архивная high-priority идея молча выпадала из окна и портация оказывалась короче N; поправлено (гидратация полным набором new-идей), добавлен регрессионный тест. Оба ревьюера (новые handle, старые не пережили сессию): BLOCKING нет, 15 находок в concerns — включая тот же класс дефекта ещё раз (scope:team идея тоже может выпасть из review=top тем же путём — не исправлено, в concerns) и независимо найденный обоими ревьюерами баг клавиатуры (действие без фокуса строки применяется к первой идее в списке). 435 тестов, ruff чист. R12.4/R24/R25/R32i/G03.1/G08/A03 закрыты."
    },
    {
      "id": "14",
      "title": "Генератор проекта и переход в VS Code",
      "requirements": [
        "R25",
        "R26",
        "R27",
        "R27.1",
        "R27.2",
        "R27.3",
        "R28",
        "R29",
        "R30.3",
        "R31",
        "G03",
        "G03.2",
        "G03.3",
        "G03.4"
      ],
      "blockedBy": [
        "01",
        "08"
      ],
      "wave": 5,
      "zone": [
        "src/idea_scout/scaffold/",
        "src/idea_scout/scaffold/templates/",
        "src/idea_scout/store/store.py (только save_project, project_for)",
        "tests/test_store.py (только: убрать project_for из NOT_IMPLEMENTED_YET)"
      ],
      "status": "done",
      "retries": 0,
      "repairs": 1,
      "handoffs": 0,
      "startedAt": "2026-09-07T05:35:00+03:00",
      "finishedAt": "2026-09-07T06:45:00+03:00",
      "note": "СДАН и слит в main. Исполнитель — Codex (Terra High). Заход 1: DONE_WITH_CONCERNS без персистентных тестов (нарушение docs/executor.md п.4), код на вид корректен. Дозапрос закрыл: 17 тестов в tests/test_scaffold.py + tests/test_store_project.py. Оба ревьюера: BLOCKING нет, находок нет вовсе. 413 тестов, ruff чист. R29 (живая кросс-агентная проверка Claude Code/Codex/OpenCode) осознанно отложена на финальный сквозной прогон T15 — честная оговорка исполнителя, не пропуск."
    },
    {
      "id": "15",
      "title": "Расписание, doctor и эксплуатация",
      "requirements": [
        "R22.5",
        "R33i",
        "R33i.1",
        "R36i",
        "R38i.1"
      ],
      "blockedBy": [
        "13"
      ],
      "wave": 7,
      "zone": [
        "src/idea_scout/ops/",
        "src/idea_scout/commands/` (свои: `install-schedule`, `doctor`, `report`)",
        "docs/operations.md"
      ],
      "status": "done",
      "retries": 0,
      "repairs": 0,
      "handoffs": 0,
      "startedAt": "2026-09-08T00:00:00+03:00",
      "finishedAt": "2026-09-08T00:00:00+03:00",
      "note": "СДАН, слит в main. Исполнитель — Codex (Terra High), одна сессия, ноль формальных кругов ремонта (все правки — находки оркестратора чтением диффа или невыполненные-BLOCKING пункты ревью, закрытые точечными дозапросами в ту же сессию). Зона дополнена tests/test_ops*.py — тикет не называл tests/ явно, пробел нарезки, не круг ремонта. До ревью оркестратор поймал и закрыл: report терял team-scope идеи (include_team=True), докА ссылалась на несуществующий tests/quality/labels.json, не было теста на backup/restore (добавлен test_sqlite_wal_backup_is_consistent_and_restorable — реальный sqlite3.Connection.backup + integrity_check). Ревью (review-manifest-spec, review-craft — обе заведены заново в этой сессии, прежние handle не пережили компакцию): 1 BLOCKING по R22.5 — doctor проверял только версию CLI, не форму ответа провайдера; исправлено минимальным реальным вызовом провайдера (ok/иначе понятная причина), закрыто повторным ревью. Craft без BLOCKING, но оркестратор эскалировал одну из его non-blocking находок до фикса осознанно (детали — см. AGENTS.md §Judgement): launchd-plist не нёс PATH для CLI провайдеров модели — под минимальным PATH launchd не нашёл бы claude/codex из nvm, именно риск, названный в самом тексте тикета. Первый фикс использовал Path(executable).resolve().parent — тот же ревьюер тут же поймал, что это резолвит цель символьной ссылки и уводит в lib/node_modules у nvm-установок, точно в целевом случае фикса; исправлено на Path(executable).parent.resolve(), закрыто повторным ревью с конкретным симлинк-тестом. Попутно закрыты находки craft: тест на секрет не мог покраснеть (исправлен реальным значением в окружении), install-schedule не ловил ValueError. 449 тестов, ruff чист. Финальный сквозной прогон (pytest -m real) и сравнение LLM-провайдеров на размеченном наборе таска 08 — инфраструктура готова (tests/test_ops_real.py, ops/quality.py), сам прогон и запись чисел в docs/operations.md — отдельный шаг оркестратора, ждёт согласия пользователя на реальные side-effects (расход подписки CLI, запись в реальный projects_root, возможный запуск VS Code). R33i манифеста флипнут в done; R36i остаётся deferred (реальная работа на VPS вне рамок), его задел переносимости (без macOS-зависимостей, пути из конфига) подтверждён этим таском — текст строки манифеста дополнен. R22.5/R33i.1/R38i.1 не имеют отдельных строк в manifest.md (подномера историй без своего реестрового ряда) — закрытие видно по этой заметке и по докам, не по флипу строки."
    },
    {
      "status": "done",
      "retries": 0,
      "repairs": 2,
      "handoffs": 0,
      "id": "16",
      "title": "Паспорта новых каналов",
      "requirements": [
        "R10",
        "R37i"
      ],
      "blockedBy": [],
      "wave": 1,
      "zone": [
        "docs/sources/",
        "tests/fixtures/"
      ],
      "note": "8 паспортов, 11 фикстур · 2 дозапроса · Open Collective запрещён своими ToS",
      "startedAt": "2026-09-06T03:56:59+03:00",
      "finishedAt": "2026-09-06T04:28:15+03:00"
    },
    {
      "status": "done",
      "retries": 0,
      "repairs": 4,
      "handoffs": 6,
      "id": "17",
      "title": "Условный источник: X через стороннего поставщика данных (Reddit отложен)",
      "requirements": [
        "R10",
        "R09.2",
        "R09.3",
        "R37i"
      ],
      "blockedBy": [
        "09",
        "10",
        "16"
      ],
      "wave": 7,
      "zone": [
        "src/idea_scout/sources/conditional/",
        "docs/sources/",
        "tests/",
        "src/idea_scout/commands/collect.py (одна правка, D45)",
        "src/idea_scout/types.py (три значения перечислений, D55)",
        "src/idea_scout/config.py (два поля Config под [sources.x_apify], D55)",
        "migrations/007_x_apify_enums.sql (новый файл, D56)",
        "tests/test_types.py (три значения в ENUMS, D57)",
        "src/idea_scout/store/store.py (метод migrate(), D58)"
      ],
      "finishedAt": "2026-09-09T02:20:00+03:00",
      "note": "Полностью закрыто 2026-09-09, включая pytest -m real. Три захода Codex подряд корректно вернули BLOCKED на контрактный долг D44 (перечисления, обещанные текстом D44, не были применены к types.py/config.py — D55, к SQL CHECK в migrations/ — D56, к тест-снимку ENUMS в tests/test_types.py — D57), закрыты оркестратором точечным расширением зоны, эскалация не потребовалась. При подготовке pytest -m real найден и исправлен реальный дефект D58 (не контрактный долг): Store.migrate() падал FOREIGN KEY constraint failed на непустой базе, потому что PRAGMA foreign_keys=OFF — no-op внутри открытой транзакции миграции; на пустых фикстурах pytest -q это было не видно, вскрылось только на data/idea-scout-real-check.sqlite3 (1198 строк). Транзакция откатилась штатно, данные не пострадали; исправлено обёрткой foreign_keys OFF/foreign_key_check/ON в Store.migrate(), регрессия закрыта тестом. Малый реальный сбор по x_apify пройден: pytest -m real -k x_apify — 1 passed, резерв settled, реальный расход $0.000122 при резерве $0.00075 под 5 постов, реальный remote_run_id получен от Apify. Результат записан в docs/operations.md. Реализован ровно один маршрут x_apify (Apify, actor_id=xquik/x-tweet-scraper, monthly_limit=10000 по умолчанию), reddit_apify/reddit_official/x_official не написаны, docs/sources/reddit.md не тронут. pytest -q: 464 passed (+ два падения, не связанные с задачей: активный APIFY_TOKEN в окружении сессии и доступная macOS-команда open — оба воспроизводимо исчезают при снятии APIFY_TOKEN из окружения / не относятся к изменённым файлам), ruff чист. Сборка полностью сдана — готова к финальному ревью. Code review этап поставлен на паузу по решению пользователя: следующий агент (оркестратор Codex) проводит отдельный design/UI pass дашборда до финального ревью."
    }
  ],
  "singlePass": null,
  "tests": {
    "command": ".venv/bin/pytest -q",
    "passed": 516,
    "failed": 0,
    "deselected": 12,
    "note": "Финальный offline suite после всех review fixes; APIFY_TOKEN снят из окружения. Два dependency deprecation warnings, failures нет. Acceptance/real tests не запускались.",
    "at": "2026-09-11T14:57:46+03:00"
  },
  "debt": {
    "placeholders": [],
    "assumptions": [
      "MVP не требует ни одного ключа — пять каналов бесплатны и открыты",
      "STACKEXCHANGE_KEY и ключ поискового провайдера появятся после паспортов таска 16",
      "projects_root = <USER_HOME>/Documents/idea-scout-projects (пользователь, 2026-09-08); каталог создан, doctor подтверждает доступность"
    ],
    "emptyEnv": [
      "REDDIT_CLIENT_ID",
      "REDDIT_CLIENT_SECRET",
      "REDDIT_USER_AGENT",
      "PRODUCTHUNT_TOKEN",
      "PRODUCTHUNT_CLIENT_ID",
      "PRODUCTHUNT_CLIENT_SECRET",
      "APIFY_TOKEN",
      "TRUSTMRR_API_KEY",
      "GITHUB_TOKEN",
      "STACKEXCHANGE_KEY",
      "TAVILY_API_KEY",
      "EXA_API_KEY",
      "X_BEARER_TOKEN",
      "X_API_KEY",
      "X_API_SECRET",
      "BLUESKY_HANDLE",
      "BLUESKY_APP_PASSWORD"
    ]
  },
  "additions": [
    {
      "id": "A01",
      "parent": "R22",
      "what": "запасной API-провайдер за тем же интерфейсом",
      "status": "интерфейс есть, адаптер отложен"
    },
    {
      "id": "A02",
      "parent": "R18",
      "what": "снимок текста первоисточника на случай мёртвой ссылки",
      "status": "сдан таском 12 — RawItem.text показывается, отсутствие даёт «доказательство недоступно»"
    },
    {
      "id": "A03",
      "parent": "R16",
      "what": "листание карточек с клавиатуры",
      "status": "сдан таском 13 — j/k по строкам, Enter открывает досье, f/x — избранное/отклонить, фокус виден"
    },
    {
      "id": "A04",
      "parent": "R05",
      "what": "SignalObservation — класс сигналов, не являющихся денежной метрикой (звёзды, скачивания, просмотры, голоса, взносы)",
      "status": "в контракте и в таске 03"
    },
    {
      "id": "A05",
      "parent": "R10",
      "what": "граница discovery: поисковая находка транзитна, право хранить проверяется воротами политики",
      "status": "в контракте и в таске 10"
    }
  ],
  "coverage": {
    "ran": true,
    "editions": 2,
    "findings": 18,
    "fixed": 16,
    "detail": ".autopilot/2026-09-05-idea-scout--wip/review-log.md",
    "note": "G2 пройден для обеих редакций. Редакция 2 поймала регрессию: при переписывании из спеки выпали пять из восьми источников, названных пользователем."
  },
  "concerns": [
    "T15 (preflight T07): «полезность источника» описана тремя разными наборами чисел — спецификация (принесено / прошло фильтр / уровень A-B / избранное), тип SourceStats (items_fetched / ideas_created / accepted_metrics) и прежний критерий T07 (получено / сохранено / прошло фильтр). Расхождение разрешает T15, когда будет писать source_usefulness; данные для любого из вариантов T07 оставляет пригодными",
    "Preflight T07: паспорта источников написаны прозой, а SourcePolicy — структура. Для Hacker News все двенадцать полей выводятся однозначно, но commercial_status и delete_sync_required выводятся из отсутствия оговорки, а не из прямой цитаты. Для источников T09 это стоит проверить до адаптера",
    "TrustMRR выключен до письменного разрешения (G09) — уровень verified опирается на самопубликуемые платёжные дашборды",
    "Разработка идёт в двух средах: Claude Code — оркестратор, Codex — исполнитель тасков. Правила в AGENTS.md и docs/executor.md",
    "T01: uvicorn не входит в согласованный список зависимостей, а T12 (FastAPI) он понадобится — решение оркестратора, добавляется отдельно",
    "T02: шесть из восьми источников — исход «не подтверждён» по условиям площадок (Indie Hackers, Acquire, Flippa, X, плюс TrustMRR выключен). T10 неисполним как записан; T09 идёт на Reddit+PH с оговорками. Решение по охвату — за пользователем",
    "T01 отложено до приёмки: двенадцать кортежей в types.py дублируют Literal и не используются — второй источник правды",
    "T01 отложено до приёмки: NOT_IMPLEMENTED_YET в tests/test_store.py:58 ведётся руками, мимо него прошли шесть заглушек",
    "T01 отложено до приёмки: test_init_is_repeatable (tests/test_cli.py:91) утверждает только код возврата, риск «повтор затёр базу» не покрыт",
    "T01 отложено до приёмки: независимость четырёх измерений (tests/test_store.py:111) доказана сырым UPDATE мимо публичного API",
    "T01 отложено до приёмки: имя test_migrations.py:32 обещает «без пропусков», утверждений про пропуски нет; ветка миграции с номером ниже применённого не покрыта",
    "T02: цитаты условий Reddit и Hacker News из среды ревью не подтвердились (прокси/SPA) — признаков пересказа нет, но T09 обязан сверить их с живой страницей при первом реальном прогоне",
    "T02: ремесленное ревью не проводилось намеренно — таск не пишет кода, проверка на выдуманный факт сделана сверкой цитат с первоисточниками",
    "ЗАКРЫТО final review 2026-09-11: migrate.py гасит только отсутствие schema_migrations; остальные sqlite3.OperationalError пробрасываются и покрыты regression test",
    "План перенарезан 2026-09-06 после исследования допустимости источников: T09 и T10 переписаны, добавлены T16 (паспорта новых каналов, готов к запуску) и T17 (условные источники, отложен до решения пользователя). Решения D01–D04 в манифесте",
    "T17 не начинается без письменного условия старта: одобрение Reddit OAuth и/или решение по X API за ~$10/мес, плюс 2–4 недели замера пользы MVP. Reddit и X одновременно не подключаются",
    "Пилот MVP на пяти бесплатных каналах должен отработать и быть измерен до подключения любого платного источника — иначе неизвестно, чего не хватает",
    "МОСТ: codex_implement не работает — жёстко передаёт --full-auto, удалённый в codex-cli 0.153.2. Воспроизводится стопроцентно. Мост также возобновляет сохранённую сессию вместо новой, то есть вызов может приземлиться в чужой разговор",
    "ЗАКРЫТО 2026-09-08 решением D48: Open Collective для MVP не используется, разрешение не запрашивается. Класс сигналов «финансирование» остаётся незакрытым в этой сборке — это принятая граница, а не долг. Приёмка R10 не страдает: подтверждены три класса (внедрение, проблема, внимание).",
    "T16: справочная статья Product Hunt про RSS отдала 403 — цитата про сам фид не снята, процитировано только условие API",
    "T16: у X три поля SourcePolicy остались «не подтверждено» (срок хранения, delete-sync, передача модели) — Developer Agreement дословно не снят",
    "T16: условия Tavily и Exa не содержат ни запрета, ни разрешения на хранение — режим transient выбран нами, а не продиктован ими",
    "Накладка параллельной работы: посредник Codex на несколько минут унёс фикстуры T16 в карантин, приняв их за вывод чужой сессии моста. T16 пересобрал образцы, потерь нет — проверено, 22 файла, все парсятся",
    "T03 отложено до приёмки: в store.py модуль types импортируется вторым путём под именем evidence_types, одно имя ре-экспортируется присваиванием",
    "T03 отложено до приёмки: date.fromisoformat повторяется трижды, помощника рядом с _dt нет",
    "T03 отложено до приёмки: имя _SIGNAL_TYPES совпадает по написанию с types.SIGNAL_TYPES и значит другое",
    "T03: потолок в два дозапроса превышен сознательно — третий круг за дырой в связке «факт ↔ идея», открытой моим же исправлением контракта D06. Два из трёх кругов были дефектами контракта оркестратора, а не промахами исполнителя",
    "ЗАКРЫТО final review 2026-09-11: одиночное ProductMention больше не поглощает метрику явно названного другого продукта; EN/RU clause-local attribution и anonymous first-person покрыты regression tests",
    "T03 отложено до приёмки: сегмент со словом-сигналом к модели не отправляется никогда — «1200 stars, около двух тысяч в месяц» теряет денежную часть",
    "T03 отложено до приёмки: MetricKind «installs» больше не производится ничем, установки пишутся сигналом под kind=downloads",
    "T03: три возврата BLOCKED подряд — все три оказались настоящими дефектами контракта оркестратора (D05, D06, D07), ни один не был промахом исполнителя. Контракт был недоопределён именно на стыке evidence↔store↔config; третий тупик решён общим правилом для ключей конфига, потому что затрагивал ещё T05, T10 и T15",
    "T03 отложено до приёмки: число 3 (потолок вызовов модели) живёт в трёх местах — шаблон config.toml, умолчание поля Config, умолчание параметра extract; проверка «целое не меньше нуля» написана дважды",
    "Волна 2: три инфраструктурных находки оркестратора при первом заходе — isolation:worktree Agent-тула несовместим с фоновым Codex (worktree подчищается раньше кода, см. AGENTS.md); исполнитель не должен сам писать в interfaces.md даже объявляя свой ключ конфига по D07 (правило теперь явно в docs/executor.md); песочница Codex не может создавать index.lock в общей .git/worktrees/ — коммиты тасков 04/05/06 сделаны оркестратором вручную после независимой перепроверки pytest/ruff",
    "T04 отложено до приёмки: identity.resolve помечает совпадение по общему домену только косметически (reason=«domain:shared-platform»), на выбор IdeaRef/Candidate это не влияет",
    "ЗАКРЫТО final review 2026-09-11: unmerge выбирает service snapshot по точному merge-log id, keep/absorb и порядку записи; пользовательский magic prefix не может подменить snapshot",
    "T04 отложено до приёмки: ProductIdentity.human_status собирается в known_identities(), но resolve() его не читает — либо для правила «rejected не наследуется» нужна проверка, либо поле лишнее",
    "T05 отложено до приёмки: test_handler_runs_outside_sql_transaction_and_completion_is_persisted не доказывает отсутствие открытой транзакции во время работы обработчика — сам runner.py по коду вызывает обработчик вне store.tx(), но тест это не проверяет",
    "T06 отложено до приёмки: ProviderChain.complete — третья ветка (providers[0].complete(...) в конце) недостижима мёртвым путём, при этом сделала бы лишний реальный вызов, если когда-нибудь станет достижима",
    "T06 отложено до приёмки: _CliProvider.complete дублирует обработку timeout/returncode до цикла повтора и внутри него",
    "T06 отложено до приёмки: test_claude_evaluate_uses_exact_isolation_flags_and_stdin проверяет отсутствие .env/.autopilot в tempfile.TemporaryDirectory — тавтология, свежий временный каталог не может их содержать независимо от кода провайдера",
    "ЗАКРЫТО 2026-09-08 решением D47: изоляция ради фолбэка evaluate не ослабляется. Переключение Claude→Codex остаётся только для research; при лимите Claude скоринг ждёт в очереди с next_attempt_at и ничего не теряет. Приёмка G03/R22.2 («ноль инструментов вообще» при оценке) сохранена в неприкосновенности.",
    "Урок 2026-09-07: шов доказательства нельзя держать в теле теста, названного про другое. Живая проверка суточного потолка обнаружения (30 вызовов, 31-й отказ) жила внутри теста с именем про окно свежести; когда окно сняли решением D25, вместе с ним молча ушло и доказательство потолка. Поведение осталось верным, доказательство исчезло, счётчик пройденных тестов этого не показал",
    "Урок 2026-09-07: из четырнадцати находок волны 4, приведших к решениям, семь оказались пробелами контракта, а не промахами исполнителей. Повторяющийся класс «страж написан, но не сторожит» имел источником двусмысленность контракта, а не невнимательность: необязательный параметр, значивший две несовместимые вещи (D23); протокол, не требовавший паспорта (D24); поле, которого не было при паспорте, который его требует (D19, D28); строка паспорта «raw_payload — элемент целиком» рядом с разделом, этот элемент запрещающим (D30). Последняя прямо породила критическую находку первого круга таска 09",
    "T09 отложено до приёмки: тред, оборванный по причине «unpaged» (Algolia не дала nbPages), выбрасывается из очереди с текстом «комментариев больше потолка» — потеря названа неверной причиной (hackernews.py:317)",
    "T10 отложено до приёмки: правило D24/D16 «паспорт читается статично, а не через getattr» покрыто только полным отсутствием policy — провайдер с policy на экземпляре мутацию переживает; pytest.raises(TypeError) на пропущенный config утверждает поведение языка, а не модуля",
    "ЗАКРЫТО 2026-09-07: долг T09 по стражам, переживавшим подмену реализации. Девять мутаций проверены стендом, все девять краснеют — пять стражей круга ремонта 2 (тред HN уходит из очереди только дочитанным; тред дочитывается постранично, а не первой сотней; две ветви window_progress — сокращение очереди как продвижение и непустая очередь как незаконченная работа; SE оставляет поток недочитанным при пропавшем конверте; GitHub стоит по остатку квоты на успешном ответе), плюс retry_after у RSS (Retry-After) и у SE (backoff), плюс случай D34 (owner есть, owner.link = None) — теперь закреплён фикстурой, а не только тестом с меткой real. Заведён tests/test_window.py: страж общий на четыре источника, и у него была покрыта одна ветвь из трёх. Реализация не менялась ни строкой — поведение было верным, не хватало доказательства. 331 тест на main.",
    "Волна 4 закрыта таском 08 (2026-09-07). Пробел нарезки: зона тикета не называла store.py/migrations/config.py, хотя store.py уже резервировал save_score/latest_score/level·theme-фильтры под owner 08, а порция unreviewed_top требовала своего ключа конфига — исправлено оркестратором до первой строки кода, кругом ремонта не считается.",
    "Таск 08, круг ремонта 1: оркестратор поймал чтением диффа (не тестами) настоящий дефект реализации — scoring/service.py считал уровень двумя функциями, публичная compute_level (её звал rescore.py) хардкодила пороги 7.5/5.5, приватная _level_with_rubric (только score()) честно читала config/rubric.yml. Правка порогов в конфиге молча не долетала бы до rescore — прямое нарушение критерия «веса и пороги в конфиге». Сведено к одной функции; закреплено тестом-мутацией, доказывающим llm.calls==0 при смене порога.",
    "Таск 08, круг ремонта 2: два независимых ревьюера (манифест+спека и ремесленный) сошлись на одной находке без сговора — 20 размеченных случаев в tests/quality/ различались только homepage/currency/profile, а метки категорий (старый кейс, дубли, скриншот, нет метрик) не были подкреплены содержимым; ни один тест не проверял handlers/score.py. Обе находки — BLOCKING: нет по вердикту ревью, отправлены на ремонт решением оркестратора как реальные пробелы приёмки, а не стиль. Исправлено: у каждой категории свои входные данные, добавлен tests/test_handlers_score.py.",
    "T08 отложено до приёмки: compute_level(axes, weights) неявно различает голые веса и полную рубрику по наличию ключей weights/thresholds во втором аргументе — сигнатура из interfaces.md сохранена буквально, но поведение узнаётся только чтением тела функции (находка ремесленного ревью, не блокирующая).",
    "T08 отложено до приёмки: main_metric в store._preview остаётся None — чужая, ещё не закрытая часть T03 (главная метрика превью), не в зоне T08.",
    "T12 отложено до приёмки: signal_summary считается для API, но нигде не отрисовывается в _PAGE как сводка одной фразой («денег не подтверждено, внедрение подтверждено трижды») — только сырой список сигналов построчно (находка манифест+спека ревью).",
    "T12 отложено до приёмки: _preview() в web зовёт store.raw_items_for(item.idea_id) второй раз в том же запросе только ради attribution — Store._preview уже делает этот же вызов ради primary_source_url (находка ремесленного ревью, двойная выборка на строку).",
    "T12 отложено до приёмки: _PAGE = _PAGE.replace(...) патчит уже собранный HTML/JS-шаблон подстрокой вместо правки на месте — единственная связь queue.last_success_at/retry_after со страницей; работает сейчас, но str.replace без совпадения молча ничего не делает при будущей правке текста рядом (находка ремесленного ревью).",
    "T12 отложено до приёмки: _safe_url сравнивает parsed.scheme без .lower() — ссылка вида HTTP://… деградирует до «нет ссылки» вместо распознавания, безопасно, но расходится с canonical_url в identity/__init__.py, который регистр лемматизирует (находка ремесленного ревью).",
    "Волна 5 закрыта 2026-09-07: таски 11, 12, 14 сданы и слиты. Контракт дополнен решениями D36-D41, все — preflight-находки оркестратора (до кода или до ревью), ни одна не считается кругом ремонта по вине исполнителя. 427 тестов, ruff чист. Требований закрыто 35 из 47.",
    "T11 отложено до приёмки: select_finalists читает только Page(number=1, size=1000) без учёта постраничного обхода — при более чем 1000 идей в статусе not_checked часть кандидатов молча выпадает из ранжирования без предупреждения (находка ремесленного ревью).",
    "T11 отложено до приёмки: _metric_claim_to_json/_metric_claim_from_json в store.py повторяют список из 14 полей MetricClaim, уже описанный в _claim (вне диффа таска) — три места держать синхронно при добавлении поля (находка ремесленного ревью).",
    "Preflight волны 5 (2026-09-07): три пробела найдены чтением контракта до кода. (1) Зоны тасков 11 и 14 не называли store.py, хотя _owner(\"11\"/\"14\", …) заглушки под save_research/latest_research и save_project/project_for стоят в коде с таска 01 — дополнено, миграций не требуется. (2) store.source_usefulness — заглушка владения таска 15 (волна 7, за блокером 13), а таск 12 (волна 5) требовал его в приёмке буквально — тупик очерёдности, решение D36 переносит реализацию базового метода на T12, T15 остаётся с расширенной разбивкой по классам сигналов в report. (3) IdeaFilter не нёс поля trust_level, хотя история 65 спеки требует фильтр по доверию, а ProjectResult (возврат scaffold.create_project) был назван в таблице границ модулей и нигде не определён — тот же класс дефекта, что D08. Решения D37 (поле + SQL-ветка) и D38 (полный тип ProjectResult + правило идемпотентности) записаны в manifest.md и interfaces.md до диспетчеризации.",
    "Preflight волны 6 (2026-09-07), таск 13: create_app(store) не мог передать Config в scaffold.create_project, а единственный вызывающий (commands/serve.py) — вне зоны тикета; заметка предыдущей волны «web не импортирует соседние модули» читалась как запрет ровно того, что тело таска 13 требует напрямую. Решение D42: create_app(store, config), одна санкционированная строка в serve.py (приём как у D13), заметка сужена — она была только про _safe_url. Отдельно решён пользователем открытый вопрос из тела тикета: ручная кнопка dossier работает для любой идеи (включая уже исследованную), своим версионированным ключом идемпотентности, отдельным от автоматического dossier:{id}:v1.",
    "Таск 13, заход 1: BLOCKED верно — зона не называла tests/, а существующий tests/test_web.py звал create_app(store) устаревшей сигнатурой после D42. Пробел нарезки, не круг ремонта; зона дополнена.",
    "Таск 13: два инфраструктурных сбоя оркестратора между заходами, не круги ремонта — забытый флаг --write у codex-companion.mjs task (сессия ушла в read-only, apply_patch отклонялся; sandbox не меняется на resume уже созданного read-only треда — пришлось начинать новый тред с --write с самого начала) и отсутствующий .venv в свежей git worktree (venv не версионируется, git worktree add его не создаёт — установлен вручную).",
    "ЗАКРЫТО final review 2026-09-11: review=top гидратирует team-scope идеи; behavioral API test покрывает результат",
    "ЗАКРЫТО до final review: Enter/f/x без текущей строки ничего не делают; повторная проверка current HEAD подтвердила regression coverage",
    "ЗАКРЫТО D60/final review 2026-09-11: ProjectRecord.error сохраняется в SQLite и восстанавливается `_reused()` после reload/retry",
    "NON-ISSUE final review 2026-09-11: suggested_name уже показывается в актуальном UI error feedback",
    "Таск 13 отложено до приёмки (ремесленное ревью, некритично): test_page_contains_click_keyboard_and_focus_controls утверждает подстроки исходника JS, а не поведение; test_rejected_idea_survives_repeated_collection_without_status_change не гоняет пайплайн и не мог быть красным ни при какой реализации; ProjectResult в двух тестах собран позиционными аргументами; _project_response перечисляет 8 полей ProjectResult руками; mutate(...).then(note).catch(note) продублирован трижды в _PAGE; # noqa: E501 в serve.py висит без надобности; ключ ручного dossier несёт мёртвый сегмент :v1 рядом с uuid4; set_human_status использует # type: ignore из-за нетипизированного набора статусов.",
    "Волна 6 закрыта 2026-09-08: таск 13 сдан и слит. Исполнитель — Codex (Terra High), один содержательный круг (заход с багом review=top найден и исправлен оркестратором чтением диффа до ревью, не круг ремонта). Оба ревьюера: BLOCKING нет, 15 находок — все в concerns выше. 435 тестов, ruff чист. Требований закрыто 39 из 47. Осталась волна 7 (таски 15, 17).",
    "NON-ISSUE final review 2026-09-11: очередь, последняя обработка и project errors доступны в dashboard; R38i.1 требует общей видимости исходов источников в CLI, а не полного зеркала dashboard в report/doctor.",
    "ЗАКРЫТО до final review решением D45: `idea-scout collect` проверяет устаревший паспорт и требует `--confirm-stale`; regression tests сохранены.",
    "Final review 2026-09-11: doctor secrets/never-run/rate_limited и exact period signal projection закрыты. Оставшиеся craft observations без V1 contract impact: PATH в plist замораживается на install-schedule; doctor shape probe расходует подписочную CLI-квоту; двойной regex версии, Decimal(Decimal) и ограниченность launchd fixture — не implementation blockers.",
    "Волна 7 (таск 15) закрыта 2026-09-08: расписание, doctor, эксплуатация сдан и слит. Исполнитель — Codex (Terra High), одна сессия, ноль формальных кругов ремонта. Оркестратор поймал чтением диффа до ревью и закрыл три дефекта реализации (team-scope в report, несуществующий путь к labels.json в доке, отсутствующий тест backup/restore). Ревью (заведено заново — review-manifest-spec/review-craft, прежние handle не пережили новую сессию чата) нашло 1 BLOCKING (R22.5 — doctor не проверял форму ответа провайдера) и одну craft-находку, эскалированную оркестратором вручную до фикса (PATH под launchd для CLI из nvm — центральный риск, названный в самом тексте тикета), которая при первом фиксе тут же дала вторичный баг (resolve() уводил в цель символьной ссылки) — пойман тем же ревьюером вторым проходом и исправлен. 449 тестов, ruff чист. Требований закрыто 40 из 47 (R33i флипнут done; R22.5/R33i.1/R38i.1 не имеют отдельных строк манифеста — закрытие зафиксировано здесь; R36i остаётся deferred, его задел переносимости подтверждён этим таском). ЗАКРЫТО 2026-09-08: финальный сквозной прогон pytest -m real выполнен и прошёл (docs/operations.md, раздел «Первый успешный прогон»). Три реальных дефекта найдены и исправлены по пути: D51 (объём прогона не был ограничен), D52 (боевой конфиг вместо отдельного — ошибка оркестратора, production-база пересобрана), D53 (JSON-схема score() не называла модели имена ключей — первый в истории проекта живой вызов score() проваливался на каждой идее). Сравнение Claude/Codex на размеченном наборе T08 выполнено только частично: для evaluate оно структурно невозможно по контракту D47 (Codex — unsupported_mode не по настройке, по дизайну G03); для research технически возможно, но не сделано в этом прогоне (естественного фолбэка не случилось, Claude не исчерпал лимит) — решение, продолжать ли, за пользователем. Осталась только волна 7 таска 17 (условные источники), не запускается без письменного решения пользователя.",
    "Решение пользователя D43 (2026-09-08, документ reddit_x_idea_scout_handoff.md от 2026-09-06): маршрут к Reddit и X — сторонний поставщик данных, а не официальный OAuth/API. Прямо противоречило записанному (D01–D02, «Вне рамок» спеки, §Источники AGENTS.md) — контракт приведён в соответствие 2026-09-08: манифест D43–D45, раздел «Расширение контракта от 2026-09-08» в interfaces.md, §Источники AGENTS.md, §Условные источники / §Снято / §Вне рамок / §Открытые места / §Бюджет в spec.md, тело тикета 17 переписано. D01/D02 сохранены как история и не отменены: их основание (условия площадок запрещают сбор) остаётся верным, изменилась готовность пользователя нести риск.",
    "D44: паспорт получил пятый исход «принят под риск» — площадка не разрешает, пользователь принял риск письменно. Введён, чтобы не пришлось врать в паспорте: прежний набор оставлял выбор между «выключен» (адаптер не пишется) и «разрешён» (паспорт утверждает неправду). Правило 4 «выключенный источник не звонит» механически не размывается — ноль вызовов дают только «не подтверждён» и «выключен».",
    "ЗАКРЫТО 2026-09-08 решением D49: в R29 склеены два требования. Цепочка LLM внутри парсера — два CLI (claude -p, codex exec), спека в Историях 42–50 OpenCode не называет, третьим провайдером он не делается. Совместимость генерируемого проекта с Claude Code/Codex/OpenCode (История 75, T14) остаётся в силе и проверяется живым прогоном; все три CLI на машине установлены.",
    "ЗАКРЫТО 2026-09-08 решением D46: TrustMRR закрыт для MVP — запрос на письменное разрешение не отправляется, источник остаётся выключенным. Уровень verified держится только на самопубликуемых платёжных дашбордах (Stripe/LemonSqueezy/Polar); второго якоря в этой сборке не будет. Требование R05 не снято, адаптер не пишется, паспорт trustmrr.md не меняется.",
    "Контракт D43–D45 одобрен пользователем 2026-09-08 и закоммичен. Таск 17 по его же решению НЕ запускается сейчас: выбор первой площадки, актора/провайдера, APIFY_TOKEN и месячного потолка делается непосредственно перед стартом, после короткого актуального ресёрча по §13 handoff.",
    "НАЙДЕНО 2026-09-08 оркестратором при подготовке реального прогона: _minimal_environment() в llm/providers.py разрешал дочернему CLI только PATH/HOME/LANG/LC_ALL/TERM, без USER — из-за чего claude отвечал «Not logged in · Please run /login» в stdout с кодом 0, ответ не парсился и complete() возвращал unavailable на КАЖДЫЙ вызов. Вся цепочка LLM на этой машине была нерабочей — и evaluate, и research. Невидимо до таска 15: доктор (R22.5) начал проверять форму ответа только там, а штатный pytest автономен по политике тестов и живого CLI не зовёт. Доказано: env -i без USER — «Not logged in», с USER — нормальный ответ; подмена в процессе переводит исход doctor с unavailable на ok. Отправлено исполнителю как точечная правка (D50). Касается приёмки G03/R22.2 «минимальное окружение», поэтому оформлено решением, а не тихим патчем.",
    "ЗАКРЫТО D59/final review 2026-09-11: Codex исключён из active production research-chain и doctor не запускает для него ложный shape probe; версия/login неактивного CLI остаются информационными."
  ],
  "reviewers": {
    "contractsBackend": "/root/contracts_backend_review",
    "webDesign": "/root/web_design_review",
    "securityOpsQuality": "/root/security_ops_quality_review",
    "finalLlmEvidence": "/root/final_rereview_llm",
    "finalStorageOps": "/root/final_rereview_storage",
    "finalWeb": "/root/final_rereview_web",
    "note": "Final code review V1: три исходных независимых read-only reviewer-а и три независимых targeted re-review после fixes; итог чист."
  },
  "blind": null,
  "handoffFile": ".autopilot/2026-09-05-idea-scout--wip/reddit_x_idea_scout_handoff.md"
}
