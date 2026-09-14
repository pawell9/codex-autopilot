# Adversarial architecture review — codex-autopilot design

**Дата:** 2026-09-12 · **Reviewer:** Claude Opus 5, независимый · **Предмет:** `design/00–10` + `design/STATUS.md` в текущем состоянии · **Тип:** review, не redesign и не implementation

## 0. Scope и метод

**Прочитано полностью:** `PROJECT-BRIEF.md`, `design/STATUS.md`, `design/00`–`10`, `research/00-audit-summary.md`.

**Открыто точечно, только для проверки спорных утверждений:**

- `references/official/snapshots/2026-09-12-codex-subagents.md` — наследование sandbox, custom agents, live overrides;
- `references/official/openai-links.md` — §Subagents, §Configuration Reference (multi_agent), §Build skills, §Sandbox/Approvals, §Code review, §Выявленные расхождения;
- `upstream/autopilot/phases/0-preflight.md` §6 Git; `4-plan.md` §Waves; `5-subagents.md` §Order of flight и §«Ten steps, but not ten writes»;
- `references/idea-scout-v1/runtime-state/state.js` (waves, startedAt/finishedAt, repairs), `git-log-oneline.txt`, `run-artifacts/…/review-log.md` (волна 4, FINAL CODE REVIEW), `handoff-2026-09-07-wave4-pause.md`;
- `research/04` §Fresh-context policy, `research/05` §Worktrees, `research/08` OD-06/07/11.

**Метки:** **FACT** — подтверждено источником; **OBSERVED** — зафиксировано в Idea Scout V1; **INFERENCE** — вывод reviewer. Все оценки стоимости — INFERENCE, не измерения.

Никакие файлы, кроме этого, не изменялись.

---

## 1. Короткий итог

Методическое ядро design сильное, и его не нужно переписывать: `phase × control`, три роли, cause-first routing без magic caps, current-intent final verifier, orchestrator-owned commits, write-set audit без доверия worker `files[]`, capability-based preflight. Всё это прямо подкреплено evidence Idea Scout.

Проблемы сосредоточены в execution-слое — там, где brief и ожидал основной redesign:

1. Design одновременно убирает единственный документированный механизм per-agent read-only (custom agent file) и требует технической read-only изоляции reviewer. На текущем Codex это почти наверняка превращает каждый review gate в ручной handoff. **CRITICAL.**
2. Самый частый реальный сценарий прерывания (обрыв сессии по лимиту / крэш) по протоколу заканчивается `BLOCKED` без определённого выхода. **HIGH.**
3. Bookkeeping-слой (≈20 helper-транзакций на тикет с repair-циклами) противоречит экономике, которую upstream уже измерил на реальном run. **HIGH.**
4. Next steps инвестируют в helper/schema до проверки двух экзистенциальных unknowns (E02/E03). **HIGH.**
5. Несколько решений сужают use case без необходимости: запрет auto `git init`, hard-block workers без доказанной freshness, serial writer со связкой commit-after-review, surface-based support gate.

**Verdict: DESIGN REVISION REQUIRED** — ограниченная ревизия конкретных решений (OD-06, OD-08/D-16 в части workers, OD-07 в части commit timing, OD-11, owner takeover, helper API/cadence, форма ledger) без пересмотра lifecycle, ролей и контрактов. Подробно — §8.

---

## 2. Ответы на шесть спорных design choices

### 2.1 Serial product writer вместо bounded parallel workers

**Вердикт:** для первого release serial оправдан, но обоснован не тем и зафиксирован слишком жёстко.

Evidence:

- **OBSERVED:** в Idea Scout 15 из 17 тикетов были спланированы в многотикетных волнах. По `startedAt` в `state.js` одновременно стартовали 01+02, 04+05+06, 09+10, 11+12. Волна 04/05/06 заняла ≈1 ч 50 мин (14:20→16:10) при суммарной длительности ≈4 ч 45 мин. Timestamps частично округлены вручную — порядок величины, не точное измерение.
- **OBSERVED:** «непересекающиеся» зоны на деле пересекались в registry-файлах: конфликт `config.py` при синхронизации (`71b89bc`), ожидаемые конфликты `config.py` / `.env.example` / `types.py` при слиянии 09+10 (handoff wave4-pause §4). Зоны многократно расширялись на `store.py` / `config.py` (`f68f397`, `1cb6f01` «по правилу D07», `c2a5eed`). Семантический дефект `_matches_policy` между 09 и 10: «цена параллельных worktree, и её видно только ревьюеру, читающему оба» (review-log, волна 4).
- **FACT** (Subagents): parallel рекомендован для read-heavy работы, для parallel writes — осторожность из-за конфликтов.

Выводы:

- **Parallel writers в общем checkout с disjoint zones небезопасны именно в модели этого design.** Post-write audit (06 §Zone semantics) не может атрибутировать untracked/generated changes конкретной attempt, а tests одного worker видят partial changes другого. Этот вариант не рекомендую даже для V1.x.
- **Parallel writers в отдельных orchestrator-created worktrees безопасны по записи.** Design уже содержит бо́льшую часть машинерии: exclusive leases, `waves`, integration-repair ticket для semantic conflict, expected-base landing. Реальные блокеры здесь не концептуальные, а runtime: writable roots для worktree, ignored env setup, approvals на `.git` (M2, M3).
- **Более дорогая потеря — не «нет parallel», а «review держит writer».** Commit происходит только после review (06 §Zone semantics, шаг 5), значит checkout нельзя отдать следующему тикету, пока идут review и repair-циклы. В Idea Scout было 37 repairs на 17 тикетов. См. H5.

**Рекомендация:**

- (a) V1 — один writer, но candidate фиксируется Git commit'ом до review;
- (b) bounded parallel (≤2–3) через per-ticket worktrees — gated capability после E04 + нового E10, а не structural non-goal в 09;
- (c) схема сразу parallel-ready (`attempt.checkout`, lease на checkout).

### 2.2 macOS local CLI primary, Desktop secondary, IDE unsupported

**Вердикт:** сужение Linux / WSL / cloud разумно. **IDE unsupported — избыточно** и противоречит собственному принципу design I9: решает capability, а не имя.

**FACT** (Subagents §Availability): subagent workflows работают в app, CLI и IDE extension, все на local Codex runtime. К тому же surface и build надёжно не наблюдаемы изнутри сессии, поэтому surface gate трудно реализовать честно. См. M1. Коррекция: допуск по результатам probes; surface влияет только на метку `qualified` / `probed-unqualified`.

### 2.3 Git-required + existing initial commit

**Вердикт: Git-required — оставить; запрет auto-init — изменить.**

Design смешивает два разных решения:

- «не поддерживать no-Git» — оправдано: не нужен второй механизм rollback;
- «не создавать Git» — не оправдано: `git init` не вводит второй механизм, а даёт тот же.

**FACT:** upstream `0-preflight.md` §6 — «If there is no git repo, `git init` **now**». **OBSERVED:** Idea Scout — greenfield, первый коммит `64087d8` «Планы автопилота». См. H6.

### 2.4 Не переусложнён ли ledger / runtime layer

**Вердикт: частично.**

Ядро дёшево и оправдано: один JSON, atomic replace, expected revision, owner epoch, reconciliation Git-коммита по operation-id trailer + base/tree.

Переусложнены:

- generic `transact` и каденс транзакций — H2;
- canonical prose внутри JSON — M4;
- 27 коллекций с дублированием — M5;
- полная snapshot-копия на каждую revision — M6;
- внешний JSON Schema validator — M7;
- prepared/applied journal для dispatch и liveness-модель takeover — H1, H2.

### 2.5 Не слишком ли дорог review topology для маленьких tickets

**Вердикт: topology не дорогой — оставить как есть.**

Один combined reviewer на routine ticket — минимум независимости. Это уже дешевле upstream, где было два постоянных reviewer'а (Manifest/Spec + Craft; handoff wave4-pause: «Ревьюеров ровно двое, постоянных»).

Реальные драйверы стоимости — не число reviewers:

- механика isolation — C1;
- полная церемония INTENT→DESIGN→G2→PLAN для однотикетного run — M9;
- небатченный повтор G5 — M13;
- дублирование returns в контексте orchestrator'а — M14;
- conservative risk upgrades — L5;
- отсутствие merge-эвристики для микро-тикетов — L4.

### 2.6 Hard-block product execution без qualified native freshness

**Вердикт:** правильно как запрет parent-implementation, неправильно как hard-block workers.

- **Оставить:** запрет orchestrator'у самому писать product (ядро D-16).
- **Проблема со стандартом доказательства E02** («неспособность child назвать marker — не доказательство; нужна inspectable input или official guarantee»). На текущей документации он вероятно недостижим: **FACT** — `research/04` §Fresh-context policy и `openai-links` §Subagents «Не документировано» — official docs не специфицируют объём inherited history.
- **Для worker** унаследованная история — вопрос стоимости и anchoring, а не safety: safety закрывают zone audit и независимый review.
- **Для G5 verifier** это вопрос independence, и там строгий стандарт уместен.

См. H4.

---

## 3. Findings

Формат каждого finding: **Место → Проблема → Failure scenario → Почему существующие safeguards не закрывают → Минимальная коррекция.**

### CRITICAL

#### C1. Reviewer isolation недостижима нативно при собственных запретах design

- **Место:**
  - 00 §«Что сохраняется и что заменяется» — «Удаляются: … custom TOML agents»;
  - 03 §Isolation is a qualification;
  - 06 §Reviewer read-only and isolation, п.1–3; §Guarantees and limits;
  - 07 §Conditional, строка «Independent review»;
  - 09 V1-12 и non-goal «custom TOML library»;
  - 10 OD-06, E03.
- **Проблема:**
  - **FACT** (Subagents snapshot): «Subagents inherit your current sandbox policy». Per-agent `sandbox_mode = "read-only"` документирован только через custom agent file. Live runtime overrides родителя (`/permissions`, `--yolo`) переприменяются к child.
  - Design убирает custom agent files и запрещает config edits. Но при этом требует effective read-only (п.1) либо «effective tools/roots должны исключать запись в authoritative checkout/control-root» (п.2).
  - Built-in `default` / `worker` / `explorer` наследуют `workspace-write` родителя-orchestrator'а, у которого writable root — репозиторий. Значит п.1 и п.2 нативно невыполнимы. Остаётся п.3 — ручная отдельная read-only Codex-сессия.
  - **OBSERVED:** самые результативные проверки Idea Scout требовали записи. Пример — мутационная проверка тестов («подменял реализацию и смотрел», review-log §Волна 4 закрыта), плюс живые прогоны с кэшами и артефактами. Read-only sandbox их запрещает, а создать себе disposable copy read-only reviewer не может.
- **Failure scenario:** 10-тикетный run: G2 + 10 change reviews + ~20 targeted re-reviews (при repair rate Idea Scout) + 2 раунда G5. Итого ≈30+ ручных handoff'ов «откройте чистую read-only сессию, вставьте packet, верните JSON». Пользователь autopilot-сценария этого не сделает: run застревает в `BLOCKED_REVIEW_CAPABILITY` уже на первом тикете. Другой исход — reviewer, который не может запускать тесты и возвращает `UNVERIFIABLE`.
- **Почему safeguards не закрывают:** fallback п.3 существует, но он и есть failure. Он делает gate ручным процессом, что противоречит 09 («Skill не требует от пользователя … routine gate approvals») и brief §18. E03 лишь констатирует провал; альтернативного механизма в design нет.
- **Минимальная коррекция:** переформулировать инвариант с «reviewer не может писать» на «reviewer не может **незаметно** изменить subject или ledger» — это соответствует объявленной cooperative threat model (02 INFERENCE).
  1. Subject review — immutable Git commit/tree SHA кандидата (см. H5), а не рабочее дерево.
  2. Reviewer работает в disposable export кандидата (`git archive <sha>` → `.autopilot/scratch/<run>/review-<id>/`; `git archive` не пишет в `.git`). Мутации, кэши и test outputs там разрешены.
  3. После review — integrity check:
     - authoritative checkout не изменился относительно baseline;
     - HEAD равен ожидаемому;
     - hash `ledger.json` совпадает с последней опубликованной revision.

     Нарушение → verdict недействителен, quarantine.
  4. Technical read-only — preferred там, где доступен. Разрешить один skill-shipped reviewer agent file (`sandbox_mode = "read-only"`), устанавливаемый на той же authorized setup стадии, что и Python-зависимости из 08, с preflight-отказом при live override. Обязателен только для critical axis, где design обоснованно опасается transient write-and-restore.
  5. Ручная clean session — только last resort для G5, если native verifier не qualified по H4.

### HIGH

#### H1. Abrupt interruption → takeover deadlock

- **Место:**
  - 02 §Atomic transaction — «Abrupt owner loss — probe process/session/checkout evidence… Если liveness неизвестна, BLOCKED, не timeout-based steal»;
  - 01 §Control transitions — QUIESCING → BLOCKED, `agent_liveness_unknown`;
  - 02 §Git/ledger side effects — «Если spawn состоялся, а handle утрачен, attempt считается liveness-unknown»;
  - 06 §Destructive effects, последний абзац.
- **Проблема:** не определено, какое evidence достаточно для takeover после потери сессии и кто его предоставляет. Изнутри новой Codex-сессии модель не может сопоставить процесс ОС со старой сессией и её subagents. «Probe process/session/checkout evidence» не специфицирован, а единственный автоматический выход (timeout) явно запрещён.
- **Failure scenario:**
  - **OBSERVED:** реальные остановки Idea Scout — «аварийная остановка» волны 4 (`5a7b7f6`, `ba8bbca` «после оборванного круга ремонта 1»), «ревьюеры возобновлены после сбоя лимита» (`38c1739`).
  - В V1: квота обрывает сессию после `DISPATCHED`. На следующий день пользователь запускает resume. Recovery не может доказать остановку старого owner и его child → `BLOCKED`. Условие снятия не определено → run мёртв, хотя на деле всё давно остановлено.
- **Почему safeguards не закрывают:** owner epoch защищает от stale-транзакций, но не отвечает на вопрос «когда можно стать owner». Recovery report с «exact next step» не может назвать шаг, которого нет в протоколе.
- **Минимальная коррекция:**
  - (a) user attestation («предыдущая сессия закрыта») — допустимая authority для takeover;
  - (b) quiescence evidence: нет изменений в checkout/worktree за короткое окно наблюдения; нет процессов с CWD внутри checkout (`lsof` / `ps`);
  - (c) затем epoch++ и обычный audit actual changes.

  Добавить в E02 кейс «kill parent session → состояние child agents». Если children гарантированно завершаются вместе с parent-процессом (INFERENCE, требует проверки), dispatch-liveness после потери сессии снимается целиком, и H1 упрощается до проверки checkout.

#### H2. Bookkeeping overhead противоречит измеренной экономике upstream

- **Место:**
  - 02 §Checkpoint cadence — «Обязателен перед dispatch, commit/integration…; после gate, contract amendment, integrated result, adjudication, before pause/final freeze»;
  - 02 §Atomic transaction, шаги 1–6 (включая regenerate views);
  - 02 §Structural example — 5 revisions на один тикет без repair;
  - 08 `tools/ledger.py` — «validate/read-slice/project/transact/…»;
  - 05 §Dispatch, шаг 2; 04 §Resolution, шаг 6.
- **Проблема:**
  - На тикет по happy path: route + prepared attempt → dispatch receipt → return → audit/candidate → review prepared → review dispatch → review return → commit prepared → commit applied → views. Это ≈9–12 helper-вызовов, и множитель растёт с каждым repair + re-review.
  - Каждый вызов — отдельный turn orchestrator'а: модель собирает JSON-дельту против схемы из 27 коллекций, а ошибки semantic validation порождают новые turns.
  - **FACT** (upstream `5-subagents.md` §Ten steps): «nine tickets at six writes each is a hundred and thirty turns spent on bookkeeping, which on a T3 run is a quarter of everything you do». Цель upstream — две записи на тикет. Design увеличивает это в разы.
- **Failure scenario:** 10 тикетов × ~2,2 repair → ≈200–250 helper turns. Контекст orchestrator'а растёт от helper outputs и ошибок схемы, срабатывает compaction (M8), квота уходит на ведение журнала вместо работы. Нарушается brief §5 («token and limit economics — first-class design requirement»).
- **Почему safeguards не закрывают:** budgets в 08 касаются prose-файлов, а не runtime-вызовов. E01 проверяет корректность, не стоимость. 09 не содержит экономического release-критерия (H7).
- **Минимальная коррекция:**
  1. Helper API на уровне намерений: одна команда = одна атомарная транзакция с несколькими record updates. Примеры:
     - `dispatch <ticket> --route …` — prepared attempt + lease + packet;
     - `record-return <attempt> <path>`;
     - `integrate <ticket>` — audit → commit prepared → *(Git commit)* → receipt + release lease + next_action;
     - `gate <id> <verdict> <evidence>`.
  2. Prepared/applied operations — только для эффектов, повтор которых вреден: commit, branch/worktree, destructive. Dispatch — обычное состояние attempt.
  3. Views регенерируются лениво — по `status` и на gate, а не на каждую транзакцию.
  4. Целевой бюджет ≤3–4 model-invoked helper-вызова на тикет по happy path; измеряется в E09.

#### H3. Next steps инвестируют в helper/schema до проверки экзистенциальных unknowns

- **Место:**
  - STATUS §Next exact step — «реализовать schema/helper в isolated test setup и выполнить E01–E04»;
  - 10 §Readiness verdict;
  - 09 §Release qualification sequence, п.2.
- **Проблема:** E02 (fresh context) и E03 (reviewer isolation) решают, существует ли V1 вообще: при провале execution — planning-only, review — manual. Это часы экспериментов на disposable fixture, а helper + schema + semantic validator — дни работы. Порядок обратный риску.
- **Failure scenario:** реализован `ledger.py` с полной схемой. Затем E02 показывает, что `spawn_agent` не даёт наблюдаемого контроля истории. По правилу design native execution not qualified: работа по helper частично обесценена, а форма ledger (attempts, isolation evidence, reviewer snapshot records) спроектирована под недоступный механизм.
- **Почему safeguards не закрывают:** 10 корректно говорит «failure → declared unsupported», но Plan B не предлагает и ранней проверки не требует.
- **Минимальная коррекция:** переставить порядок работ:
  1. throwaway spikes: E02, включая parent-kill и tiered freshness из H4;
  2. E03, включая варианты из C1;
  3. часть E04 про approvals и worktree placement (M2, M3);
  4. решения по C1 / H4 / M2 / M3;
  5. только затем schema, helper и E01.

#### H4. Hard-block workers на вероятно недоказуемом стандарте freshness

- **Место:**
  - 03 §Isolation — «execution нельзя подменять работой parent… native workers остаются prerequisite product execution»;
  - 05 §Dispatch, шаг 3;
  - 07 §Conditional, строка «Packet-only fresh context»; §Deliberate changes, п.1;
  - 10 OD-08, D-16, PASS-критерий E02.
- **Проблема:** одно правило применено к двум разным рискам.
  - Для **worker** унаследованная история parent — лишние токены и возможное anchoring. От неверных записей защищают lease и audit, от неверного результата — независимый reviewer.
  - Для **G5 verifier** история — прямое нарушение blind contract.

  E02 требует для обоих «tool/runtime contract и inspectable input или соответствующая official guarantee», а official docs этого не дают.
- **Failure scenario:** на текущем build `spawn_agent` не имеет документированного параметра истории. Behavioural marker-тест проходит — child не знает marker родителя, — но design не принимает это как доказательство. В итоге V1 объявлен unsupported для execution на всех surfaces.
- **Почему safeguards не закрывают:** degraded path «handoff всего run в qualified supported session» пуст, если ни одна сессия не qualifies.
- **Минимальная коррекция:** tiered standard.
  - **Worker, research и change review:** достаточен behavioural marker-тест с positive control (канал, через который история заведомо наследуется, должен marker раскрывать). Если история унаследована — `DEGRADED_CONTEXT` с записью стоимости; execution разрешён, parent по-прежнему не реализует.
  - **G5 verifier:** строгий стандарт; при `UNKNOWN` — отдельный процесс или сессия.

#### H5. Commit-after-review связывает writer с review; parallel зафиксирован как non-goal

- **Место:**
  - 06 §Zone semantics, шаг 5 — «Freeze candidate tree+manifest hash; после review/checks повторить audit… Только затем stage exact approved paths и commit»;
  - 06 §Commit and integration ownership; §Checkout policy, п.5;
  - 04 §Economics — «Worker concurrency V1 не применяется»;
  - 09 §Explicit non-goals — «parallel product writers; per-ticket merge/worktree orchestration»;
  - 10 OD-07.
- **Проблема:**
  - (a) Пока candidate не закоммичен, он живёт в рабочем дереве единственного checkout: следующий тикет нельзя начать до конца review и repair.
  - (b) «Tree + manifest hash» — самодельная замена того, что Git даёт бесплатно.
  - (c) Parallel writers зафиксированы как non-goal, а не как gated capability. При этом brief §5.7 и §7 (waves) явно предполагают parallelism при независимости тикетов.
- **Failure scenario:** **OBSERVED** — у T07 было 4 круга ремонта с эскалацией (`d4b1d40`), у T10 — 3 круга с эскалацией (`05252ac`). В V1 всё это время checkout простаивает, независимые тикеты ждут. На run масштаба Idea Scout wall-clock вырастает кратно относительно upstream (§2.1).
- **Почему safeguards не закрывают:** SHOULD «read-only concurrently» не помогает — узкое место в writer slot, а не в чтениях.
- **Минимальная коррекция:**
  - Candidate commit сразу после audit. Варианты:
    - на run branch: repair — новые commits, история не переписывается;
    - в `refs/autopilot/<run>/cand/<attempt>`, затем fast-forward/cherry-pick reviewed commit: branch чище, но больше записей в `.git`, см. M2.

    Verdict привязан к SHA; `INTEGRATED` = reviewed commit.
  - Это же даёт immutable subject для C1 и упрощает crash reconciliation.
  - В 09 заменить non-goal на «bounded parallel через per-ticket worktrees — gated capability после E10». Схема parallel-ready.

#### H6. Запрет auto `git init` отсекает greenfield

- **Место:**
  - 06 §Git-required — «skill не делает `git init` или baseline commit из всех файлов автоматически»;
  - 07 §V1 support policy, строка «No Git/unborn repo… Unsupported execution»;
  - 09 V1-11; 10 OD-11.
- **Проблема:** см. §2.3 — смешаны «no-Git support» и «auto-init». Оба факта из §2.3 (upstream делает `git init`, Idea Scout — greenfield) говорят против запрета.
- **Failure scenario:** пользователь в пустой папке говорит «собери мне бота» и получает `UNSUPPORTED` / `BLOCKED_PREFLIGHT` с отсылкой к «отдельно разрешить подготовку Git». Самый частый старт autopilot-запроса упирается в барьер без объяснимой пользы.
- **Почему safeguards не закрывают:** фраза «Пользователь может отдельно разрешить подготовку Git» не описана как flow: нет ни шага, ни владельца, ни gate.
- **Минимальная коррекция:** в G0 при отсутствии repo или unborn repo показать exact inventory папки.
  - Пустая или почти пустая папка (brief / seed-файлы) при build authority → одним подтверждением `git init` + initial commit. Secrets-паттерны исключить и назвать.
  - Непустая папка с неизвестным содержимым → явный вопрос.

  Git-required сохраняется.

#### H7. Экономика не входит в release acceptance; E07 не нагружает orchestration

- **Место:**
  - 09 §Release qualification sequence; §Completion criteria — «observed/unknown economics» только в отчёте;
  - 10 E05/E06 — tuning non-blocking; E07 — «небольшой local tool».
- **Проблема:** brief §5 и §15 требуют оценки «context growth, duplicate work, unnecessary model escalation, limit/token consumption» и сценария «harder/ambiguous… exercises escalation/review/checkpoints». E07 — один-два тикета: он не вызовет compaction и не проверит DAG, накопление returns, helper overhead, количество approvals и manual handoffs.
- **Failure scenario:** V1 проходит все MUST на micro-project. На первом реальном 10-тикетном проекте он исчерпывает квоту на bookkeeping или требует десятки ручных действий.
- **Почему safeguards не закрывают:** routing economics справедливо помечены как optimization, но overhead самого протокола — это вопрос viability, а не optimization.
- **Минимальная коррекция:** добавить E09 — disposable проект на 6–10 тикетов, 2–3 уровня DAG, одна amendment, принудительная compaction. Записывать метрики из §5: turns и tokens orchestrator'а, helper calls на тикет, agent calls на тикет, user interventions (approvals, manual handoffs). Release требует записанных чисел и явно принятого пользователем budget.

### MEDIUM

#### M1. Surface-based support gate противоречит capability-based принципу

- **Место:** 07 §V1 support policy (IDE — «Unsupported V1 execution»), §Minimum version strategy; 00 I9; 10 OD-12.
- **Проблема:** probes решают всё, кроме допуска surface — он задан ярлыком. Как orchestrator достоверно отличит CLI от IDE и app и определит build, не указано. `codex --version` из PATH может не совпадать с запущенным бинарником: IDE и app несут собственный.
- **Failure scenario:** пользователь работает в VS Code (IDE extension, тот же local runtime), все probes проходят — но run отклонён по ярлыку. Либо CLI-сессия строит fingerprint по чужому бинарнику и неверно переиспользует qualification.
- **Почему safeguards не закрывают:** правило «если version signal недоступен — fingerprint unknown» регулирует только reuse, но не допуск.
- **Минимальная коррекция:** допуск определяется результатами probes; surface — метка `qualified` / `probed-unqualified` в отчёте. Назвать источник версии или честно считать его unknown.

#### M2. Approvals на Git-операции при default preset не учтены

- **Место:** 06 §Files and ownership — «Git refs/index/commits/worktrees: Orchestrator через обычные разрешённые Git операции»; §Checkout/branch policy; 07 §Cheap, строка «Effective authority surface».
- **Проблема:** **FACT** (Agent approvals & security): в `workspace-write` `.git` read-only рекурсивно; Auto preset = `workspace-write` + `on-request`. Каждый `git commit`, `git branch`, `git worktree add` требует escalation.
- **Failure scenario:** десятки approval prompts за run. В non-interactive потоке операция просто падает (**FACT**, Subagents §Approvals: «an action that needs new approval fails»). Autopilot «без ritual approvals» на практике спрашивает на каждом тикете.
- **Почему safeguards не закрывают:** фраза «runtime approval остаётся отдельным control» (01 §Human decision points) констатирует ограничение, но не проектирует его обработку.
- **Минимальная коррекция:** явное решение в 06/07:
  - preflight детектирует approval mode;
  - рекомендованная one-time authorized стратегия — session-level разрешение точных command prefixes или prefix rule на setup-стадии;
  - batching commits;
  - счётчик approvals в E04 и E09.

#### M3. Размещение run worktree не согласовано с writable roots

- **Место:** 06 §Checkout/branch policy, п.3; абзац «Worktree path — exact resolved path внутри already authorized writable roots… не под `$HOME` по догадке».
- **Проблема:** writable root сессии — primary checkout. Возможны два варианта, и оба плохие:
  - worktree **снаружи** недоступен для записи без изменения config или запуска с дополнительным root;
  - worktree **внутри** primary — вложенная копия исходников в checkout, где пользователь «продолжает работать» (а это и есть основание для worktree mode).

  Плюс `git worktree add` пишет в `.git` — см. M2.
- **Failure scenario:** worktree в `.autopilot/wt/…` → pytest / jest / ruff / rg пользователя в его dirty checkout подхватывают дубли исходников. Либо sibling path → записи worker'а отклонены sandbox.
- **Почему safeguards не закрывают:** правило «внутри authorized roots» не выбирает между двумя плохими вариантами.
- **Минимальная коррекция:** решить явно.
  - (a) V1 — только clean checkout: dirty → попросить пользователя сохранить свои изменения самостоятельно; worktree mode становится gated capability.
  - (b) Sibling path + preflight-инструкция запустить сессию с этим writable root.

  Проверить выбранный вариант в E04.

#### M4. Canonical prose внутри JSON ledger

- **Место:** 02 §Где живёт текст — «Ledger authoritative также для canonical intent, spec и interface content»; §Canonical namespace, `views/`.
- **Проблема:** orchestrator (LLM) пишет spec и interfaces прозой, JSON-экранирует её в helper-вызовах, а затем читает сгенерированный Markdown — двойные токены и хрупкость. Правка view пользователем требует decision-import. В upstream артефакты (manifest / spec / `interfaces.md`) были Markdown и читались людьми и агентами напрямую.
- **Failure scenario:** spec на несколько тысяч слов уходит в helper одним аргументом → ошибка экранирования или лимит длины команды → повторы. G2 reviewer читает view со stale-маркером после сбоя renderer.
- **Почему safeguards не закрывают:** «одна правда» достижима дешевле — renderer и import ceremony решают проблему, созданную выбором формата.
- **Минимальная коррекция:** prose — Markdown-файлы в `.autopilot/runs/<id>/` как canonical content; ledger хранит их SHA-256 и structured state (IDs, состояния, refs). Drift = hash mismatch → тот же decision flow. Renderer для prose не нужен; generated остаются только status и report.

#### M5. Избыточность record model и расхождение с 05

- **Место:** 02 §Required top-level records (27 записей/коллекций); 05 §Legacy fields decision — CONCERNS/BLOCKERS объединены в `issues`.
- **Проблема:**
  - `repairs` и `handoffs` дублируют attempts (`mode=repair`, `status=HANDOFF` + payload);
  - `concerns` и `blockers` разделены, хотя return contract их уже слил;
  - `zones` + `leases` при одном writer — это `ticket.zone` + состояние lease на attempt;
  - `waves` при serial writes — только отображение;
  - `transitions` дублирует последовательность revisions;
  - коллекция `checkpoints` дублирует файлы в `checkpoints/`.
- **Failure scenario:** больше полей → больше semantic-validation правил → больше отказов helper на правильных по смыслу транзакциях и больше токенов на slices.
- **Почему safeguards не закрывают:** schema SSOT предотвращает расхождение определений, но не их избыточность.
- **Минимальная коррекция:** слить, как перечислено выше. Parallel-ready поле (`attempt.checkout`) оставить без отдельных коллекций.

#### M6. Полная snapshot-копия на каждую revision без retention; перегруженный термин «checkpoint»

- **Место:** 02 §Atomic transaction, шаг 4; §Checkpoint cadence and scope; запись `checkpoints` в §Required records.
- **Проблема:**
  - **INFERENCE:** к концу крупного run ledger с inline prose и сотнями records весит сотни КБ; сотни транзакций × размер → сотни МБ в `checkpoints/`.
  - При atomic rename повреждение текущего файла крайне маловероятно, поэтому все копии не нужны.
  - «Checkpoint» одновременно означает файл revision, record и каденс.
- **Failure scenario:** `.autopilot` разрастается, листинг и hash-проверки замедляются. Пользователь чистит папку вручную вместе с ledger.
- **Почему safeguards не закрывают:** E01 измеряет bytes/revision, но retention не спроектирован.
- **Минимальная коррекция:** `ledger.prev.json` + копии только на gate и перед side-effect операциями; retention последних N; развести термины.

#### M7. Внешний JSON Schema validator как runtime dependency

- **Место:** 08 §Per-file contracts — «Python 3, Git и один pinned JSON Schema validator dependency, bundled/installed при отдельной authorized setup стадии».
- **Проблема:** **INFERENCE** (знание экосистемы, не проверено в этом репозитории): актуальный `jsonschema` тянет `referencing` → `rpds-py` (compiled extension). В системном Python macOS его нет, а «никаких automatic package installs» → setup-барьер до первого run.
- **Failure scenario:** на preflight helper не может импортировать validator → `BLOCKED` на старте, пользователь разбирается с pip / venv до первой пользы.
- **Почему safeguards не закрывают:** preflight лишь детектирует отсутствие зависимости.
- **Минимальная коррекция:** helper на stdlib (закрытый набор проверок type / enum / required / unknown fields); `contracts.schema.json` — dev-time oracle в тестах helper.

#### M8. Нет правила re-grounding после compaction

- **Место:** 08 §Loading routes — «Последовательный переход между файлами… не очищает уже виденную историю»; §SKILL.md content boundary; 03 §Orchestrator context contract.
- **Проблема:** **FACT** (`openai-links` §CLI и §Config): `/compact` и `model_auto_compact_token_limit` заменяют ранние ходы summary. Phase-файлы и инварианты, прочитанные в начале, могут быть сжаты — протокол «забывается» посреди EXECUTE.
- **Failure scenario:** после auto-compaction orchestrator пропускает prepared-запись перед commit или сам «чинит мелочь» между return и review.
- **Почему safeguards не закрывают:** semantic validator helper ловит только то, что проходит через helper. Действие без helper-вызова (прямой commit, правка файла) он не видит.
- **Минимальная коррекция:** правило в SKILL.md — после compaction / resume и перед каждым side effect вызывать `ledger.py brief`: phase, next_action, путь текущего phase-файла, 5–8 инвариантов строками. При сомнении — перечитать phase-файл. Проверять в E09.

#### M9. Церемония lifecycle не масштабируется с размером run

- **Место:** 01 §Gates — G2 independent reviewer всегда; 08 §Full mapping #3 — «DROP T0–T3/manual/full quotas»; 10 OD-09. Brief §7 перечисляет «project tiering» среди сохраняемого.
- **Проблема:** tiering заменён только в routing и review, но не в глубине фаз.
  - Однотикетный routine change проходит INTENT → DESIGN → G2 reviewer → PLAN → worker → reviewer → G5, плюс preflight и десятки транзакций.
  - Пользовательский режим «покажи план перед сборкой» не предусмотрен; есть только manual final approval.
- **Failure scenario:** «добавь флаг `--json` в CLI» стоит ≥4 agent calls и значительный orchestration overhead. Skill на практике перестают применять к небольшим задачам.
- **Почему safeguards не закрывают:** OD-09 определяет, какой model и reviewer нужен, но не сколько фаз проходить.
- **Минимальная коррекция:**
  - Compact path с явными критериями входа: все тикеты routine, ≤2 тикета, нет public interface и data migration. В нём DESIGN+PLAN — один артефакт, G2+G3 — один reviewer, G5 без изменений.
  - Опциональные user checkpoints (approve spec/plan) — как intent-level policy.

#### M10. Нет межпрогонной project memory

- **Место:** 10 OD-10; 01 §Control transitions / Разрешённые возвраты (successor run «с ссылкой на checkpoint»); 07 §Capability record — между runs переносятся только capability facts. Brief §7 — «project memory».
- **Проблема:** решения и контракты принятого run не попадают в intake следующего; ledger локален и untracked.
- **Failure scenario:** Idea Scout V2 (заявленная цель) стартует без D01–D62 и interfaces V1. Решения выводятся заново или противоречат принятым; G2 не может проверить silent narrowing относительно прежних решений.
- **Почему safeguards не закрывают:** запрет автоматической записи в `AGENTS.md` правильный, но чтение для intake записи не требует.
- **Минимальная коррекция:** на INTENT/DESIGN successor run читает final report и decisions/contracts view последнего ACCEPTED run (read-only) и фиксирует их как prior decisions. Export в project docs — только явным deliverable.

#### M11. Опасности untracked `.autopilot` не закрыты

- **Место:** 02 §Canonical namespace — «`.autopilot` не включается в product commits V1…, `.gitignore` автоматически не изменяется»; ledger остаётся в control-root даже при run worktree.
- **Проблема:** ledger лежит в checkout, где пользователь продолжает работать. **OBSERVED:** в Idea Scout `.autopilot/` был в `main` (handoff wave4-pause §Состояние). **FACT:** upstream `0-preflight.md` §6 явно не игнорирует `.autopilot/`.
- **Failure scenario:** `git clean -fdx` или `git stash -u` пользователя уничтожает ledger; `git add -A` коммитит `.autopilot` в продукт; инструменты сканируют `scratch/`.
- **Почему safeguards не закрывают:** фраза «Локальный ledger переживает interruption, но не… удаление checkout» — признание ограничения, а не защита.
- **Минимальная коррекция:** на bootstrap, с authority, добавить строку `.autopilot/` в `.git/info/exclude` — это локально и не project-owned файл. В report — явное предупреждение про `git clean` / `git stash -u`.

#### M12. Routing deadlock при ненаблюдаемой фактической модели child

- **Место:** 04 §Resolution algorithm, шаг 4 — «Coupled/critical task с unknown adequacy возвращается к decomposition/qualification»; 07 §Model discovery protocol, п.4.
- **Проблема:** если runtime не сообщает модель child (вероятно), unknown actual model читается как unknown adequacy для всех coupled/critical задач.
- **Failure scenario:** critical тикет бесконечно декомпозируется или получает `BLOCKED capability`, хотя child просто унаследовал модель и effort orchestrator'а.
- **Почему safeguards не закрывают:** fallback graph заканчивается `BLOCKED capability`.
- **Минимальная коррекция:** без запрошенного override adequacy inherited route = adequacy route orchestrator'а (известен из конфигурации сессии). Unknown actual model учитывается только когда override был запрошен.

#### M13. Повтор G5 после repair не батчится

- **Место:** 01 §Разрешённые возвраты phase — «после repair G4/G5 выполняются заново»; 05 §Final independent verifier, последний абзац.
- **Проблема:** не сказано, что findings одного G5 раунда исправляются одной repair-волной перед новым G5.
- **Failure scenario:** **OBSERVED** — FINAL CODE REVIEW Idea Scout нашёл 19 root defects. При последовательной интерпретации правила — до 19 полных blind verifier раундов.
- **Почему safeguards не закрывают:** no-progress guard ограничивает повторы без нового evidence, но не стоимость корректных повторов.
- **Минимальная коррекция:** все accepted findings G5 раунда → одна repair wave (targeted re-reviews внутри) → один fresh G5.

#### M14. Return transport удваивает токены и теряет завершённые returns при падении orchestrator

- **Место:** 02 §Где живёт текст — «Worker не пишет даже собственный return в `.autopilot`»; 03 §Shared resources; 05 §Dispatch, шаг 5; §Malformed returns.
- **Проблема:** return приходит в контекст orchestrator'а, затем модель повторно эмитит тот же JSON в helper-вызов. Если сессия падает между получением и записью, завершённая работа восстанавливается только «fresh inspection» — ещё одним agent call.
- **Failure scenario:** review с 20 findings (порядка нескольких тысяч токенов) дважды проходит через контекст orchestrator'а. Квота обрывается сразу после return — reviewer запускается заново.
- **Почему safeguards не закрывают:** `LOST` / `INTERRUPTED` + fresh inspection корректно, но дорого для самого частого случая.
- **Минимальная коррекция:** worker пишет return JSON в attempt-specific путь в `scratch/` (по 02 это «not state»), а transport message содержит только статус и путь. Helper ingest'ит файл по пути, валидирует и хеширует. Для technically read-only reviewers — message transport как fallback.

### LOW

#### L1. Двойное значение G4

- **Место:** 09 §Lifecycle — «per-ticket write audit/review/integration (G4)»; 01 §Gates — G4 = run-level EXECUTE → VERIFY.
- **Проблема:** одно имя для per-ticket цикла и run-level gate.
- **Failure scenario:** тесты implementation, написанные по 09 (acceptance contract), валидируют G4 на каждом тикете или не проверяют run-level G4 — gate records расходятся с 01.
- **Почему safeguards не закрывают:** карта нормативных владельцев в 00 делает владельцем 01, но тесты пишут по 09.
- **Минимальная коррекция:** переименовать per-ticket цикл в 09 («ticket integration check»).

#### L2. Risk уровня плана не определён

- **Место:** 01 G3 — «orchestrator + plan reviewer для elevated/critical»; 04 §Task assessment — risk per task.
- **Проблема:** не определено, что такое elevated plan.
- **Failure scenario:** план с одним critical тикетом (migration) проходит G3 без plan review, потому что «run не critical».
- **Почему safeguards не закрывают:** агрегат не определён ни в 01, ни в 04.
- **Минимальная коррекция:** plan review обязателен, если хотя бы один тикет elevated или critical.

#### L3. Сетка 4 capability classes × 4 reasoning bands без evidence различимости

- **Место:** 04 §Task assessment.
- **Проблема:** **FACT** (Subagents): текущий catalog для subagents — три рекомендованные модели плюс effort. Сетка 4×4 и resolver описывают комбинации, которые реально сводятся к 2–3 вариантам.
- **Failure scenario:** лишние enum и правила в `routing.md` и схеме; resolver пишет binding records для неразличимых вариантов.
- **Почему safeguards не закрывают:** E05 tuning non-blocking; упрощение не запланировано.
- **Минимальная коррекция:** 3 route tiers + frontier escalation; resolver-алгоритм не меняется.

#### L4. Вместе с квотами удалена merge-эвристика для микро-тикетов

- **Место:** 08 §Full mapping #9 — «ticket-count rules removed»; upstream `4-plan.md`, «The neighbour test».
- **Проблема:** квоты справедливо убраны, но вместе с ними пропала эвристика слияния соседних микро-тикетов, которая снижала число agent calls.
- **Failure scenario:** план режет трёхстрочные правки в отдельные тикеты — у каждого ≥2 agent calls и полный цикл транзакций.
- **Почему safeguards не закрывают:** G3 проверяет исполнимость плана, а не стоимость нарезки.
- **Минимальная коррекция:** вернуть neighbour test как рекомендацию `plan.md`, не как квоту.

#### L5. Conservative risk upgrades без обязанности снять неопределённость

- **Место:** 04 §Task assessment — «Неопределённая risk classification → elevated до уточнения, uncertainty о destructive effect → critical».
- **Проблема:** безопасный default без триггера пересмотра.
- **Failure scenario:** в новом проекте большинство тикетов остаются elevated «до уточнения», которое не наступает → лишние risk mandates.
- **Почему safeguards не закрывают:** нет правила, когда и кем tier пересматривается.
- **Минимальная коррекция:** при upgrade по неопределённости записывать resolving question и пересматривать tier после ответа или research.

---

## 4. Сводка по запрошенным осям

| Ось | Оценка | Findings |
|---|---|---|
| Соответствие цели Codex-native Autopilot | В целом соответствует; отклонения — tiering, project memory, waves, `.autopilot` вне Git, git init | M9, M10, H5, M11, H6 |
| Внутренние противоречия 00–10 | Одно существенное (custom agent files vs read-only reviewer); остальные терминологические | C1, M5, M6, L1, L2 |
| Сложность / лишние abstraction layers | Форма ledger, helper API, routing vocabulary | H2, M4–M7, L3 |
| Недостающие invariants / failure paths | Takeover, compaction, crash между return и записью | H1, M8, M14 |
| Lifecycle и resume | State machine хорошая; resume ломается на liveness | H1 |
| JSON ledger / locking / checkpoint / reconciliation | Ядро верное, обвес избыточен | H2, M4–M7 |
| Task/return contracts, context isolation | Контракты хорошие; transport и tiering freshness — нет | H4, M14 |
| Reviewer independence | Принципы верные; механизм нативно недостижим | C1 |
| Safety / write / Git / worktree | Audit и ownership сильные; approvals, placement, commit timing — нет | M2, M3, H5 |
| Model / reasoning routing | Верная capability-first логика; deadlock при unknown model | M12, L3 |
| Preflight и runtime discovery | Cheap/conditional/deep — верно; surface gate — нет | M1 |
| Progressive disclosure / 16 файлов | Структура хорошая: ≈5,3–8,8 тыс. слов prose на весь orchestration путь; нет re-grounding | M8 |
| Достаточность E01–E08 | См. §6 | H3, H7 |
| Стоимость context / tokens / agent calls | См. §5 | H2, M9, M13, M14 |
| Реальное использование на текущем Codex | Блокируется C1, H1, H4, M2 | — |

---

## 5. Оценка стоимости

**INFERENCE, не измерено.**

Допущения:

- 10-тикетный run;
- repair rate ≈2,2 на тикет — это Idea Scout 37/17, верхняя оценка: контракты V1 могут её снизить;
- смешанный routine / elevated risk;
- каденс транзакций — как в 02.

| Показатель | Design как есть | После H2, M13, M14, C1 |
|---|---|---|
| Agent calls на тикет | worker 1 + reviewer 1 (+ axis ~0,3) + 2,2 × (repair worker + re-review) ≈ 6,7 | то же — topology не меняется |
| Agent calls на run | G2 1–2 + G3 0–1 + 10 × 6,7 + G5 раунды ≈ 75–80 | ≈ 70–75 (G5 батчится) |
| Helper calls на тикет | ≈ 3 на agent call + 2 на commit ≈ 20–25 | ≈ 6–8 |
| Helper turns на run | ≈ 200–250 | ≈ 60–80 |
| Prose skill-файлов в контексте orchestrator | ≈ 5,3–8,8 тыс. слов один раз, повторно после compaction | то же + короткий `brief` |
| Рост контекста orchestrator на тикет | returns × 6,7 + helper outputs + повторная эмиссия returns ≈ 15–30 тыс. токенов | ≈ 8–15 тыс. (returns по пути) |
| Ручные действия пользователя | ≈ 30+ review handoffs (если C1 не решён) + approval на каждую Git-операцию | 0 handoffs штатно; approvals — по стратегии M2 |

**Вывод:** число reviewers — не главный драйвер. Главные — isolation mechanics, bookkeeping turns и дублирование returns в контексте orchestrator'а. На run такого размера compaction почти гарантирована, поэтому M8 обязателен.

---

## 6. Достаточность E01–E08

| Experiment | Достаточен? | Чего не хватает |
|---|---|---|
| E01 ledger | Да, для корректности | Retention и размер (M6); стоимость helper-вызовов (→ E09); takeover по user attestation (H1) |
| E02 native context | Нет | Tiered PASS-стандарт (H4); кейс «kill parent session → children»; наблюдаемость фактической модели child (M12) |
| E03 reviewer isolation | Нет | Arm «skill-shipped reviewer agent file ± live override»; arm «commit-SHA subject + disposable export + integrity check» (C1); опциональный arm `codex exec -s read-only` с проверкой nested Seatbelt, network и approvals; возможность мутационных проверок |
| E04 Git / worktree | Частично | Число approvals при Auto preset (M2); worktree placement vs writable roots (M3); greenfield `git init` flow (H6); hazard `git clean` / `stash -u` (M11) |
| E05 routing | Да (functional) | — |
| E06 review topology | Да | — |
| E07 micro-project | Да, для happy и alternate paths | Не нагружает orchestration; compaction не возникает |
| E08 adversarial | Да | Кейс «после compaction orchestrator пропускает protocol step» (M8) |
| **E09 — новый** | — | 6–10 тикетов, DAG 2–3 уровня, amendment, forced compaction, метрики §5 (H7) |
| **E10 — новый, post-V1** | — | Bounded parallel workers через per-ticket worktrees: конфликты registry-файлов, семантический cross-ticket дефект, integration-repair (H5) |

---

## 7. Итоговые списки

### KEEP AS IS

- `phase × control` state machine, legal phase returns, amendment → STALE (01).
- Три роли; repair — режим worker; research и final — мандаты reviewer (D-13).
- Orchestrator никогда не пишет product; single-agent fallback отсутствует (ядро D-16).
- Cause-first triage, no-repeat-without-progress, никаких magic repair caps (OD-03) — прямо подтверждено 37 repairs / 7 handoffs Idea Scout.
- Current-intent final verifier без implementation narrative; per-criterion `UNVERIFIABLE` блокирует G5 (D-14, D-20).
- Worker не коммитит; orchestrator коммитит exact path list с повторным audit. **OBSERVED:** коммит T10 без `config.py` был пойман только сверкой коммита с рабочей копией (review-log §Волна 4 закрыта).
- Post-write audit не доверяет `files[]` worker'а (06).
- Git reconciliation через operation-id trailer + base/tree (02).
- Ядро ledger: один JSON, atomic replace, expected revision, owner epoch.
- Review topology defaults (OD-05): combined reviewer для routine, risk axis для elevated, отдельная ось для critical, fresh final.
- Frontier / Astra / external review — optional (OD-04).
- Форма worker packet и return; COMMIT удалён из worker return (05).
- Cheap / conditional / deep preflight с fingerprint invalidation (07, кроме surface gate).
- 16-файловая progressive disclosure; explicit invocation через `allow_implicit_invocation: false` (08).
- Никаких dashboard/server, автоматических правок AGENTS/config, auto-stash/reset/clean.
- Git-required как принцип (OD-11, кроме запрета init).
- Serial writer как default первого release (OD-07, с коррекциями H5).

### SIMPLIFY

- Helper API: intent-level составные транзакции; prepared/applied — только для вредно-повторяемых эффектов; ленивые views (H2).
- Prose — canonical Markdown с hash в ledger (M4).
- Слить `repairs` / `handoffs` → attempts, `concerns` / `blockers` → issues, `zones` / `leases` → ticket zone + attempt lease; `waves` / `transitions` / `checkpoints` — derived (M5).
- Checkpoints: prev + gate / pre-side-effect + retention; развести термины (M6).
- Stdlib-validator вместо внешнего JSON Schema dependency (M7).
- Reviewer isolation: три уровня → commit-SHA subject + disposable export + integrity check. Technical read-only — где доступен; manual session — last resort для G5 (C1).
- Candidate identity: Git commit вместо самодельного tree + manifest hash (H5).
- Routing vocabulary: 3 tiers + frontier escalation (L3).

### CHANGE BEFORE IMPLEMENTATION

**До начала кода** — дорого менять после реализации схемы и helper:

- **C1** — переопределить reviewer isolation invariant; разрешить skill-shipped reviewer agent file на authorized setup-стадии.
- **H1** — takeover protocol: user attestation + quiescence evidence.
- **H2** — форма helper API и каденс транзакций.
- **H3** — порядок работ: spikes E02 / E03 / часть E04 → решения → schema/helper → E01.
- **H4** — tiered freshness standard (worker vs G5).
- **H5** — candidate commit до review; parallel — gated capability, схема parallel-ready.
- **H6** — greenfield `git init` flow с подтверждением.
- **M2, M3** — стратегия Git approvals и размещение worktree (или отказ от worktree mode в V1).
- **M4, M5** — форма ledger.
- **M8** — re-grounding rule.
- **M12** — adequacy inherited route.
- **M14** — return transport по пути.

**До release** — можно вносить по ходу implementation:

- **H7** — E09 и экономический release-критерий.
- **M1** — probe-based допуск surfaces.
- **M6, M7** — retention и stdlib-validator.
- **M9** — compact path.
- **M10** — intake предыдущего accepted run.
- **M11** — `.git/info/exclude` + предупреждение в report.
- **M13** — батчинг G5.
- **L1–L5.**

### VALIDATE BY EXPERIMENT ONLY

- Контроль истории у `spawn_agent` и behavioural marker-тест с positive control (E02, H4).
- Судьба child agents при kill parent session (E02) — может убрать dispatch-liveness целиком (H1).
- Эффективность reviewer agent file с `sandbox_mode = "read-only"` с live override и без; видит ли модель собственную sandbox policy (E03).
- `codex exec -s read-only` со structured output как reviewer transport внутри sandboxed сессии: nested Seatbelt, network, approvals. Только как arm E03; не принимать без evidence и не превращать в bridge.
- Native `/review` как transport change review (уже SHOULD в 09).
- Число approval prompts при Auto preset; worktree placement (E04, M2, M3).
- Hooks (`PreToolUse` как zone guard, `SubagentStop` для return validation) как опциональный preventive слой — только при authority на config, не требование V1.
- Protocol adherence после compaction и overhead-метрики (E09).
- Bounded parallel workers через per-ticket worktrees (E10, post-V1).
- Утечка implementation narrative в blind verifier через комментарии и decision-ID в исходниках (E08).
- Routing economics и comparative review topology (E05, E06 — как в design).

---

## 8. Verdict

# DESIGN REVISION REQUIRED

**Обоснование.**

- **C1:** на текущем Codex design в собственных ограничениях почти наверняка не может выполнять независимые review gates без ручного участия пользователя.
- **H1:** самый частый реальный resume заканчивается `BLOCKED` без определённого выхода.
- **H4:** execution может оказаться unsupported целиком.

Это не редакционные правки. Они меняют принятые решения OD-06, OD-08 / D-16 (часть про workers), OD-07 (commit timing), OD-11 (init), модель takeover и форму helper/ledger — то есть ровно то, что STATUS и 10 объявили закрытым.

**Объём ревизии ограничен.** Lifecycle, роли, packet/return контракты, cause-first routing, current-intent final verifier, принципы safety и ownership, файловая архитектура остаются как есть. После внесения пунктов CHANGE BEFORE IMPLEMENTATION (блок «до начала кода») и выполнения spikes E02/E03 design можно считать готовым к реализации без повторного полного архитектурного pass.
