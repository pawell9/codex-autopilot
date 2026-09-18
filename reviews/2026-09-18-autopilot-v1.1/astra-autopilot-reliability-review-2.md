# Codex Autopilot v1.0.11 — независимый reliability review

**Дата:** 18 сентября 2026 года.  
**Исследованный source commit:** `642dc87693374cc03be407cc302cbcb136576713`.  
**Реальный run:** `2026-09-17-idea-scout-v2-successor`, revision 58, ticket `T02-R17`.  
**Результат:** 14 объединённых findings: **7 P0, 5 P1, 2 P2**; спроектировано 42 qualification-сценария.

## 1. Executive verdict

**Продолжать T02 на v1.0.11 как обычный автономный repair→review→integrate цикл не рекомендую. Нужен новый release Autopilot и отдельный, сохраняющий историю recovery revision 58. Предпочтительный scope — v1.1.0: структурное укрепление существующего helper, без переписывания методологии и всей системы с нуля.**

Найден не один missing `affected_refs`, а несколько классов несогласованности соседних transitions. Главные: разные определения current finding/candidate; authorization, которую нельзя исполнить или заменить; competing ingest paths; более слабый integration gate; незамкнутый effect recovery; невычисляемый `next_action`. Дополнительно **сам current frozen bundle revision 58 не соответствует текущему input/output validator**: есть 13 active input/producer intersections. Этот последний факт нельзя устранить одним finding-binding patch.

Самое опасное независимо воспроизведённое поведение: после принятого review **BLOCK** команда `integrate` принимает другие, schema-valid **PASS** bytes из того же inbox. Получается `ticket=INTEGRATED`, новый `return_ref`, но `attempt.review_result=BLOCK`, два противоречащих review records и `run.control=BLOCKED`. Другой probe принимает `PASS` с independent check `failed`, а critical ticket интегрируется по одному routine review с receipt `{"status":"PASS"}`. Это не описание случившейся интеграции Idea Scout: **это контрпримеры исходному v1.0.11 на изолированных fixtures**. [S: `tools/ledger.py:1434–1463,1831–1855,2842–2937`; AP-P03, AP-P04.]

Положительные свойства подтверждаются: owner/revision fencing для большинства публикаций; `flock`, атомарная запись файлов с fsync; immutable object publication; строгий schema subset; exact-inbox/packet/epoch проверки; duplicate ingest no-op; хорошие negative tests actual write-set и transitive lineage; narrow recovery commands сохраняют исходные worker returns; continuation candidate не допускается напрямую в integrate. Это полезная база. Но **наличие безопасных локальных predicates пока не означает согласованность всей state machine**. [S: `tools/ledger.py:246–280,610–664,1281–1426,1831–1950,2354–2571,2983–3144`; AP-P12, AP-P13; исходные tests.]

### 1.1. Что фактически проверено

Сокращения ссылок в этом отчёте:

- **S:** путь внутри `autopilot-hardening-source(1).zip`.
- **E:** путь внутри `autopilot-hardening-evidence(1).zip`.
- **AP-Pxx:** наблюдение из `audit-evidence/probe-results.json`; воспроизводящий код — `audit-evidence/reproduce_lifecycle_gaps.py`.

Ссылки `S:tools/ledger.py:...` — номера строк приложенного исходника, не номера строк этого отчёта. JSON evidence адресуется именем файла и полем/ID; названия вроде `bind-findings` ниже — **предлагаемые events**, не существующие CLI-команды.

| Проверка | Независимый результат | Ограничение |
|---|---|---|
| Source MANIFEST | 59/59 SHA-256 совпали | MANIFEST доказывает состав пакета, не полноту исходного repo |
| Evidence source-index | 54/54 packet hashes совпали | 17 entries redacted, в основном state-related artifacts |
| Evidence SHA256SUMS | 57/57 совпали | Не является подписью доверенного runtime |
| Ledger snapshots | 15/15 прошли `validate_ledger(..., verify_files=False)` | Не проверялись отсутствующие абсолютные project-local document/object paths |
| `unittest discover -s tests -v` | 80 entries: **71 PASS, 1 SKIP, 6 ERROR, 2 FAIL** | Все 8 errors/failures объясняются отсутствующими dependencies/fixtures в source packet |
| Дополнительные isolated probes | 16/16 дали ожидаемые наблюдения | 2 — positive controls; AP-P08/AP-P16 — predicate-level probes, не полные E2E |
| Реальные R58 contract bindings | Pure binding validator отвергает; 13 intersections | Полный `current_design_publication` требует отсутствующих canonical docs и здесь не исполнялся |

Пропущены/не включены: `tools/dashboard.py`, `upstream/autopilot/tools/sync.py`, `experiments/v1_40_ticket_qualification.py`, `experiments/v104_lifecycle_qualification.py`, E03M fixtures; некоторые instruction documents тоже отсутствуют. Это **дефект воспроизводимости пакета**, а не доказательство отсутствия файлов в полном repo. Заявленные release qualification/installation parity нельзя объявить независимо подтверждёнными. Один opt-in test skipped по своему условию. Исходные тесты запускались в отдельной Linux/Python 3.13 среде; результаты продуктовых тестов Idea Scout из reviewer return не переисполнялись: application checkout не приложен. [S: MANIFEST.json, tests; E: source-index.json, evidence-manifest.md; audit-evidence/baseline-unittest-complete.txt.]

**Не проверено:** реальный Codex spawn/wait/stop transport; полный installed runtime; исходный Git checkout Idea Scout; полный object store; оригинальная hash chain redacted ledgers; точные отсутствующие fault snapshots 32/37/47/52. По этим точкам выводы ограничены соседними snapshots, retained objects и кодом. Review04 return в evidence явно **not-ingested**, его findings не включены в число canonical findings.

### 1.2. Основные воспроизведения

| Probe | Наблюдение v1.0.11 |
|---|---|
| AP-P01 | `prepared→uncertain`; последующее разрешение отвергается: `only a prepared operation can be reconciled` |
| AP-P02 | Real Git continuation commit: `reconcile-effect applied` проходит, `preserve-blocked-candidate` после него отвергается; candidate остаётся null |
| AP-P03 | Ingest BLOCK → другие PASS bytes в том же inbox → integrate проходит, оставляя противоречивые durable поля |
| AP-P04 | PASS с failed independent check проходит; critical ticket интегрируется без separate critical qualification и с minimal receipt |
| AP-P05 | Обычный allow∩deny path получает lease; worker return с неправильным ticket_id принимается |
| AP-P06 | После `cancel` в QUIESCING можно dispatch READY ticket |
| AP-P07 | `recover` переводит terminal CANCELLED run в RECOVERING |
| AP-P08 | Repair source-review допускается dispatch, но preservation provenance validator требует source-worker |
| AP-P09 | Modify-only repair dispatch принимает base, не совпадающий с current candidate |
| AP-P10 | Повтор causal signature проходит authorize; dispatch отказывает; изменённую unused authorization на READY заменить нельзя |
| AP-P11 | Finding с known refs без ticket принят, authorize отказывает; next_action остаётся await |
| AP-P12 / AP-P13 | Exact duplicate worker/review ingest — корректный no-op, revision не меняется |
| AP-P14 | `reconcile-effect unchanged` записывает abandoned; exact retry отвергается |
| AP-P15 | Exact prepare-review retry отвергается по reused attempt ID вместо idempotent adoption |
| AP-P16 | No-change closure отвергает previous BLOCKED candidate до возможности проверить его continuation receipt |

## 2. Reconstructed state machine

### 2.1. Реальная композиция, а не одна линейная диаграмма

```text
PREFLIGHT → INTENT → DESIGN → PLAN → EXECUTE → VERIFY → ACCEPT
                         G2     G3                 G4       G5/G6

Ортогональный control:
ACTIVE / QUIESCING / PAUSED / BLOCKED / RECOVERING / ACCEPTED / FAILED / CANCELLED

Обычный ticket:
PLANNED → READY → RUNNING → CANDIDATE → REVIEW → INTEGRATED
                       ↘ BLOCKED ↗ authorize-repair → READY → fresh worker

Worker attempt:
PREPARED → RETURNED(status=DONE|BLOCKED|FAILED|HANDOFF)
        ↘ LOST / INTERRUPTED

Review attempt:
PREPARED → RETURNED(verdict=PASS|BLOCK|UNVERIFIABLE)
        ↘ LOST / INTERRUPTED

Lease:
active → released
active → quarantined → [только узкие recovery paths в v1.0.11]

Effect:
prepared → applied | uncertain | abandoned
                         ↑
       заявленный выход из uncertain в модели не реализован reconcile-effect

Candidate фактически хранится внутри worker attempt:
none → DONE candidate
none → continuation-only candidate (BLOCKED/HANDOFF + proof)
```

`DISPATCHED` есть в схеме/декларативной модели и проверках, но `dispatch` сохраняет `PREPARED`; отдельного реализованного start event, который делал бы `DISPATCHED`, не найдено. Это не доказательство отсутствия spawn: helper вообще его не выполняет. Native runtime может фактически работать, пока durable attempt остаётся PREPARED. В design разрешено объединённое подтверждение dispatch/return, но без выдуманных timestamps; в реализации полноценный runtime start receipt отсутствует. [S: `tools/ledger.py:1–8,1953–2043`; design/01-lifecycle-state-machine.md; references/ledger.md:99.]

`current_candidate` **не существует как отдельное durable поле**. Он выводится через `ticket.current_attempt→attempt.candidate_sha`. Поэтому новая попытка с candidate=null скрывает предыдущий candidate, даже если тот должен оставаться базой. `close-blocked-attempt` вынужден возвращать current_attempt назад. `REPAIR` есть как допустимый ticket state, но authorize практически делает `REVIEW/BLOCKED→READY`, не отдельную фазу REPAIR. Waves/ready queues/transition lists **заявлены derived**, не отдельные durable сущности; отсутствие коллекции waves само по себе не bug. [S: tools/ledger.py:2072–2173,3147–3344; references/ledger.md:18.]

### 2.2. Terminal / non-terminal семантика

| Сущность | Terminal в текущем замысле | Что это НЕ означает |
|---|---|---|
| Run | ACCEPTED / FAILED / CANCELLED | recover не должен оживлять terminal run; сейчас может — REL-07 |
| Attempt | RETURNED / LOST / INTERRUPTED | RETURNED не значит продукт DONE; lease может ещё резервировать checkout |
| Worker result | DONE / BLOCKED / FAILED / HANDOFF — окончательный result этой попытки | BLOCKED attempt может дать continuation candidate; ticket/run остаются non-terminal |
| Ticket | INTEGRATED / CANCELLED / STALE для данной версии | INTEGRATED не окончательная run acceptance; amendment может invalidate applicability |
| Review | Принятый immutable return завершает review attempt | PASS не достаточен без integrity/required axes; BLOCK не должен переписываться PASS |
| Candidate | Явного terminal lifecycle нет | continuation candidate не integratable; historical candidate не удаляется |
| Lease | released — закрыта authority/reservation данного lease | Released без exact stop evidence не доказывает, что реальный процесс остановлен |
| Effect | applied / abandoned задуманы как закрытые | applied effect может ещё не быть adopted как candidate; uncertain non-terminal, но сейчас тупиковый |
| Finding | Только impact/invalidated_by и ссылки | Нет полноценного разделения resolved defect / superseded subject / current obligation |

### 2.3. Durable transitions и их соседние команды

Общее для обычного `transaction`: fixed run lock, owner token, exact revision, copy, transition, usage/provenance, revision+1, previous hash, validation, publication. Успешный exact replay некоторых команд возвращает прежний result до revision check; это корректно лишь при полном identity match. Не все команды имеют одинаковый replay guard. Atomicity ledger-файла не покрывает Git/spawn и несколько последующих snapshot writes. [S: tools/ledger.py:246–280,610–664.]

| Transition | Входные условия и durable изменения | Lease / candidate / findings | next_action и следующий путь / recovery | Код |
|---|---|---|---|---|
| `init` | Новый run namespace; существующие runs в control root должны быть terminal; rev0, owner/settings/repository | Нет attempts/candidates/findings | preflight → publish-intent; нельзя overwrite existing run | 1666–1703 |
| `publish-intent` | Единственная initial binding canonical intent; subsequent edits через amend | Новые docs/intent, без product worker | G1/adopt requirements; interrupted bootstrap можно продолжить в том же run | 4014–4114 |
| `adopt-requirements` | Exact intent/epoch, validated manifest, records + migration receipt | Requirements/criteria, не ticket execution | DESIGN current requirements; exact replay/no-change conflict guards | 4117–4211 |
| `publish-design-bundle` | DESIGN, exact current intent, schema/DAG/zones/bindings; immutable docs/contracts/tickets/routes/publication | Tickets PLANNED; старые publications superseded при допустимом design repair | prepare_g2_coverage_review; ordinary execution-stage republish не является универсальным recovery | 4668–4805 |
| `prepare-design-review` | Current bundle, registered identity/role, coverage/plan kind, exact fingerprint/version | Review PREPARED, empty-zone active lease | await_design_review_return → validate/ingest; malformed/interrupt → terminate/retry | 2708–2787 |
| `validate-return` | Read-only schema + state/packet-bound semantics | Не меняет ledger, lease, findings | Исправить invalid return до первого ingest либо остановить attempt; не считать validation исполнением | 1531–1547 |
| `ingest-return` design review | Matching inbox/hash/run/attempt/epoch/current bundle | RETURNED, reviewer released, finding/issues/review rows | Current coverage/plan PASS может быть использован G2/G3; BLOCK требует repair; next_action не всегда пересчитан | 1831–1950 |
| `migrate-review-currentness` | Exact current design publication и fresh review evidence | Invalidate только provably old publication lineage; unknown остаётся blocker | Не предназначен для T02 candidate finding bindings | 4373–4652 |
| `gate` G2/G3 | Coverage/plan PASS текущего bundle, no blockers, strict self-produced input check, correct phase edge | Product lease не создаётся; ticket PLANNED/READY | EXECUTE → ready-ticket; user checkpoint только по реально требуемой authority policy | 4871–4940 |
| `ready-ticket` | ACTIVE EXECUTE, current publication ticket PLANNED, integrated deps, active criteria/inputs | Ticket READY; нет lease | dispatch_ticket → dispatch. Second ready call после success не general idempotent | 2046–2069 |
| `authorize-repair` | REVIEW/BLOCKED/REPAIR; blocking non-invalidated finding/issue bound to ticket; stopped attempts; narrow source validation | Releases same-ticket active reservations; stores exact contract object/decision; READY; candidate остаётся через old current_attempt | dispatch_repair либо dispatch_repair_with_blocker_retained. Signature/ordinary-source mismatch может возникнуть позже | 2072–2173 |
| `dispatch` | READY, packet identity/epoch, route if supplied, integrated deps, repair auth + effective lease | New PREPARED/active lease; current_attempt заменён; RUNNING; spawn counter++ | await_worker_return. Native spawn/wait вне helper; no-start/lost → terminate/recovery | 1953–2043 |
| `ingest-return` worker DONE | Exact return + worker semantics; declared changes внутри effective lease | RETURNED, return ref; ticket обычно остаётся RUNNING; lease active | audit_worker_return_and_prepare_candidate → actual audit → prepared Git effect → candidate | 1831–1950 |
| `ingest-return` BLOCKED/FAILED/HANDOFF | Matching semantically valid return | Attempt RETURNED; ticket/run BLOCKED; issues persisted; lease active, если нет violation | triage_or_repair; files=[] repair может close; files≠[] BLOCKED/HANDOFF может preserve; FAILED не имеет такого preserve | 1831–1950 |
| Worker write-set violation | Declared path/operation вне lease | RETURNED + quarantined lease; BLOCKED; ownership issue | Узкая reconcile-quarantined-attempt только legacy case; прочее требует bounded recovery/termination | 937–960,1831–1950 |
| `audit-write-set` | Root + baseline + declared paths + zones; inspect tracked/untracked/ignored/rename/type/symlink/mode | Read-only audit receipt; сам не публикует candidate/lease resolution | candidate/preserve после PASS; rejected foreign effects не удалять | 2983–3144 |
| `prepare-effect` | Unique operation ID and effect parameters, owner/revision | prepared operation; не Git commit | apply_prepared_effect вне helper → candidate или reconciliation | 2574–2592 |
| `reconcile-effect` | Сейчас только prepared; receipt для applied; optional Git observations | applied / uncertain / abandoned + receipt | applied→resume_after_effect_reconciliation, но candidate не принимает applied; uncertain требует недоступное разрешение | 2595–2652 |
| `candidate` | Worker RETURNED DONE, active lease, prepared candidate_commit, PASS SHA/tree receipt | candidate_sha/tree on attempt; ticket CANDIDATE; operation applied; lease retained | review_change → prepare-review; no direct BLOCKED/HANDOFF | 2209–2258 |
| `preserve-blocked-candidate` | Exact current BLOCKED ticket/W, BLOCKED/HANDOFF nonempty return, typed scoped blocker, owner auth, required proofs, direct commit/audit, prepared op | Continuation receipt + candidate; original return unchanged; BLOCKED remains; active reservation retained | review or candidate-bound repair; integrate explicitly rejects | 2261–2571 |
| `prepare-review` | Current frozen worker candidate; CANDIDATE/REVIEW либо BLOCKED audited continuation | Review PREPARED/active empty zone; ordinary ticket REVIEW, continuation остаётся BLOCKED | await_review_return / await_blocked_candidate_review | 2655–2705 |
| `ingest-return` ordinary review | Exact identity/fingerprint of registered review; schema and semantics | Reviewer RETURNED/released; findings + mirrored issues + verdict rows | BLOCK/UNVERIFIABLE sets BLOCKED but may retain await; PASS often also retains await; disagreement has explicit adjudication action | 1831–1950 |
| `adjudicate` | Evidence-backed decision tied to existing reviews | Invalidations/dispositions, no majority-vote substitute | continue_after_adjudication; should not overwrite immutable returns | 2790–2839 |
| `integrate` | Generic review PREPARED/RETURNED, supplied PASS bytes, basic integrity receipt, current linked worker candidate; continuation denied | Ticket INTEGRATED; worker/reviewer released; new review record; repaired issue/finding mutation | next_action not reliably updated; G4 only when ALL current required tickets complete; REL-03/04 gaps | 2842–2937 |
| `close-blocked-attempt` | Exact current no-write BLOCKED **repair**, no unresolved effect, clean actual HEAD/tree=base, previous same-ticket candidate RETURNED/released/DONE | Releases failed lease, restores old current_attempt, preserves history, BLOCKED remains | Changed authorization→fresh worker. Prior continuation rejected; initial BLOCK/HANDOFF/FAILED outside scope | 3147–3344 |
| `reconcile-quarantined-attempt` | Specific legacy create→modify repair DONE; current/source/base/authorization + fresh full audit | Quarantine→active; exact issue advisory/invalidated; immutable reconciliation receipt | prepare_candidate_effect. Same receipt replay after later lease release not fully supported | 3347–3714 |
| `terminate-attempt` | PREPARED/DISPATCHED; LOST/INTERRUPTED; release requires PASS writer_stopped; old epoch cannot release here | Terminal attempt; released/quarantined lease; affected current ticket BLOCKED; termination issue/evidence | recover_attempt→fresh attempt only after valid reuse. General lease recovery incomplete | 2176–2206 |
| `prepare-handoff` / `import-manual` | Exact manual critical/G5 bundle/environment/context/integrity contracts; stricter qualification | Handoff/return/evidence, controlled reviewer authority | Manual protocol; not a replacement for missing routine review; downstream integration must consume qualification | 3728–4011 |
| `amend` | Current authorized intent, new version + authority; impact closure | Invalidates dependent evidence/records, versions intent; not silent patch of contracts/history | Return to affected gates with fresh worker/review; preserve partial work | 4808–4868 |
| `gate` G4/G5/G6 | All current tickets integrated, leases/effects closed, blockers absent, current acceptance where required | Run EXECUTE→VERIFY→ACCEPT→ACCEPTED | T02 alone does not allow G4 because T03–T11 remain planned | 4871–4966 |
| `cancel` / `cancel --finalize` | First QUIESCING; then writers stopped/effects reconciled receipt | Inflight interrupted, unfinished cancelled, leases released, run terminal | Preserve owned partial state; explicit successor, not implicit reset/clean | 4969–5001 |
| `recover` | Verified current/prev/snapshot, owner/revision; optional takeover token/epoch | RECOVERING; takeover quarantines inflight authority; does not itself reconcile Git | inspect pending effects/attempts. It currently permits terminal resurrection — gap | 5004–5036 |
| `status/brief/diagnose/render-view` | Read-only state inspection; unknown schema diagnose-only | Projections not execution authority | `status` current counts use invalidated_by only; stale next_action is returned as stored | 1706–1830 |
| `publish-usage` | Attributable usage event | Counters/evidence/revision, no product change | Does not prove real spawn occurred; telemetry separate from state correctness | 1726–1830 |

### 2.4. Самые важные разрывы соседних transitions

`ingest review → authorize`: отсутствует ticket binding. `authorize → dispatch`: поздняя causal-signature/provenance проверка. `dispatch repair → preserve`: разные допустимые source types. `continuation → no-change repair → close`: предыдущий BLOCKED candidate не подходит DONE-only restore. `reconcile applied → candidate`: incompatible operation state. `uncertain → reconcile`: guard запрещает собственный вход. `ingest BLOCK → integrate PASS`: второй writer path нарушает immutability. `review return → next_action`: producer завершён, action остался await. `cancel QUIESCING → dispatch`: нет общего run guard. `terminal predecessor → recover`: может возникнуть новый nonterminal owner вне successor-init guard.

Каждый из этих разрывов либо непосредственно воспроизведён, либо подтверждается сочетанием реального evidence и точных predicates. **Увеличение числа отдельных recovery-команд без shared transition contract повторит тот же архитектурный паттерн.**

## 3. Audit известных incidents A–L

### A. Contract binding lifecycle — prevention частичный, existing-run compatibility не закрыта

Новый `validate_ticket_contract_bindings` безусловно запрещает `ticket.id ∈ contract.producer_refs` для любого input из `ticket.contract_refs`; он вызывается при публикации и G2/G3. Исходные tests подтверждают early rejection self-produced proposed contract и отказ тихо переинтерпретировать mixed legacy bundle. Предшественник действительно прошёл через rev119→readiness BLOCK rev120→QUIESCING rev121→CANCELLED rev122. [S: tools/ledger.py:865–892,4744–4751,4871–4940; tests/test_design_publication.py; E:state/predecessor/rev-119-gate.json…rev-122-cancel-terminal.json.]

**Однако текущий successor не соответствует этому же guard.** В rev58 current publication содержит **13 input/producer пересечений**; все соответствующие contracts active. Например, T02 потребляет `CT-V2-ARCHITECTURE-R17`, который называет T02 producer; T03 потребляет собственные ARCHITECTURE и RUNTIME. Pure validator, применённый к точным archived полям current publication, отвергает T02. Это не буквальное повторение «proposed contract не active»: `ready-ticket` смотрит active status и такие поля не отсекает, а G2/G3 predicate строже. Полный G2 здесь не запускался из-за отсутствия project-local canonical docs. [E:state/successor/rev-058-ledger.json#/contracts,/tickets,/design_publication; audit-evidence/revision58-binding-revalidation.json.]

Поэтому «A полностью закрыт» — слишком сильный вывод. Закрыт конкретный новый-publication вход. Остаются explicit migration текущего legacy bundle, смысл accepted spec против implementation output, cross-ticket availability и внешний proposed input, который тест специально оставляет late readiness blocker. Нельзя автоматически удалить все 13 refs: возможно, некоторые отражают использование принятого архитектурного ограничения при реализации этого же контракта; как правильно разделить эти роли, без canonical документов неизвестно. **REL-10 P0** — compatibility assessment до T02; дальнейшая executable readiness qualification обязательна до T03.

### B. Worker dispatch / await — instruction исправлена, runtime guarantee отсутствует

`SKILL.md` и `phases/execute.md` однозначно определяют `await_worker_return` как внутреннее ожидание, не user checkpoint: bounded intervals до 60 секунд; после трёх no-progress intervals — проверить handle/inbox, остановить либо LOST/INTERRUPTED recovery. Worker DONE ingest действительно меняет next_action на audit/candidate. Это подтверждают исходные тесты. [S:SKILL.md:68–80; phases/execute.md:6–10; tools/ledger.py:1953–2043,1831–1950; tests/test_lifecycle_repairs.py.]

Но ledger не spawn-ит, не владеет turn, не возобновляет host автоматически и не доказывает остановку child process. Исправленная инструкция повышает вероятность правильного поведения оркестратора; она **не гарантирует** его при разрыве сессии, quota, app interruption или ошибке native wait. Нужен receipt-based adapter/protocol, а не бесконечная петля в prompt. В evidence нет достаточного runtime trace для количественной оценки «как часто останавливался await». **REL-08/14**.

### C. Create → repair modify — локальный класс закрыт с оговорками

`effective_worker_lease` умеет расширить create-only ticket path до modify только для exact same-ticket candidate-bound repair; требуется packet allow, отсутствие deny, authorization и path lineage до original create. Stored provenance содержит expanded entries, source, candidate/base и authorization. Positive/negative tests этого класса прошли. [S:tools/ledger.py:1134–1426; tests/test_lifecycle_repairs.py.]

Граница не должна исчезать ради удобства: нельзя превращать ticket create zone в общий modify-anywhere. Вместе с тем unexpanded modify path обходит некоторые candidate/deny predicates, а current source type по-разному проверяется preservation — **REL-02/09**. Из того, что create→modify работает, не следует, что все repair write-set combinations согласованы.

### D. Уже quarantined attempt — узкий auditable recovery есть, general recovery и replay неполны

В rev33 W02 reconciliation действительно сохраняет original return, фиксирует старую lease, точную новую modify zone, prior W01 candidate, finding/auth refs и actual write-set audit; quarantine issue становится advisory/invalidated. Это не «ручное разжатие lease» без следа. [E:state/successor/rev-033-quarantine-reconciled.json; receipts/worker02-reconciliation-receipt.json; S:tools/ledger.py:3347–3714.]

Нельзя смешивать SHA в receipt: `candidate_sha` reconciliation — **предыдущая проверенная база** `b5ce…`, а позднейший W02 candidate — `ea51…`. После reconciliation rev33 attempt ещё не имеет нового candidate; commit/candidate publication — отдельные steps. Формулировка incident report «return and commit existed» не доказывает, что именно reconciler завершил новую candidate publication или что новый commit уже был текущим HEAD в момент этой команды. [E:receipts/worker02-commit-receipt.json; state/successor/rev-033-quarantine-reconciled.json; последующие snapshots.]

Повтор с тем же receipt поддержан, пока сохраняется ожидаемое промежуточное состояние. Но replay после downstream lease release конфликтует с требованием active recovered lease. Lost/Interrupted/non-DONE/foreign-path quarantine намеренно не покрываются этой командой; им всё равно требуется безопасный отдельный путь. **REL-08**, qualification Q09/Q40.

### E. Transitive repair provenance — сильная реализация внутри узкого envelope

`validated_repair_path_lineage` рекурсивно проверяет same-ticket candidate/base chain, exact original create, modify с consumed authorization и preserve hop для untouched path. Циклы, stale/forked base, foreign ticket/path, отсутствующий validated origin отвергаются. Existing tests для двух и нескольких repairs и preserve hops прошли. [S:tools/ledger.py:1209–1366; tests/test_lifecycle_repairs.py; E:state/successor/rev-038-repair-authorized.json.]

Остаются ограничения: оригинальный create допускается в `mode=implement`, но не как впервые созданный path в repair; когда base совпадает у нескольких candidate attempts, fallback ищет unique parent по SHA и может блокировать legitimate no-op history — это надо решать explicit parent ID, не ослаблением fork guard. Source-review разрешён верхним валидатором, но lower lineage/preservation ожидают worker в отдельных местах. Обычный modify не проходит тот же freshness proof. Нужен единый canonical parent worker, а историческая authorization должна оставаться доказательством происхождения даже после resolution finding. **REL-02**.

### F. BLOCKED без файлов — закрыт только точный repair с DONE-предшественником

W04 files=[] закрыт в rev48 с full no-change audit, restored W03 pointer и released W04 lease. Original attempt/return не удалены. Tests отвергают dirty checkout, stale base и наличие candidate. [E:attempts/worker04-return.json; receipts/worker04-blocked-closure-receipt.json; state/successor/rev-048-blocked-attempt-closed.json; S:tools/ledger.py:3147–3344.]

Этот переход не покрывает initial no-change BLOCK, empty HANDOFF/FAILED, interrupted/lost worker и, особенно важно для следующего T02 repair, **no-change BLOCK поверх continuation candidate**: restore требует exact previous DONE return. AP-P16 изолирует этот predicate; source подтверждает, что continuation receipt даже не может заменить DONE condition. General outcome closure — **REL-08**, текущий continuation edge — **REL-02 P0**.

### G. Authorization, которую нельзя dispatch — исправлено конкретное missing source, не весь класс

Rev49/50 подтверждают узкое replacement unused authorization05→06 с `source_attempt_ref`. Текущий authorize проверяет наличие/смысл source, когда нужен transitive create→modify. Старый missing-source READY контракт можно supersede, сохранив историю. [E:authorizations/repair-auth-05-defective-contract.json; repair-auth-06-rebound-contract.json; state/successor/rev-049-defective-authorization.json; rev-050-rebound-authorization.json.]

Однако AP-P10 воспроизводит новый экземпляр той же архитектурной ошибки: unchanged signature принимается authorize и отсекается dispatch; заменить такой READY контракт уже нельзя, потому что legacy/provenance-rebind exception не подходит. Нужен shared feasibility validator и обычный revoke/replace lifecycle **для всех** unused authorizations. Сам owner token не означает, что authorization executable. **REL-02**.

### H. BLOCKED/HANDOFF с полезным write-set — guarded preservation работает, следующий цикл не полностью замкнут

W05: base `9aa550…`, три modify paths, sole failed full-suite check при passing focused checks; direct commit `ef8da4…`; preserved rev54; original BLOCKED, external blocker и active reservation сохранены. Нельзя интегрировать такой candidate напрямую. Guard проверяет exact current attempt/epoch, issue source/type/scope, owner authorization, return refs, required check attribution, repair provenance, actual HEAD/tree/direct parent/cleanliness, declared vs actual write set и operation binding. Это существенно сильнее обычного candidate path. [E:attempts/worker05-return.json; receipts/worker05-continuation-receipt.json; state/successor/rev-053-effect-prepared.json; rev-054-continuation-preserved.json; S:tools/ledger.py:2354–2571.]

Ограничения: source-review vs source-worker mismatch; ordinary repair без source допускается dispatch, но не preservation; no-change repair after continuation не закрывается; reconciled applied effect не принимается publication. Кроме того, код не требует, чтобы `required − external_checks` содержал хотя бы один положительный focused proof: владелец может атрибутировать все required failures внешнему blocker. Для HANDOFF пропущена проверка полного соответствия unsatisfied criteria внешнему набору, которая есть для BLOCKED. Это **проверки допустимости proof**, а не доказательство злонамеренности пользователя или ложности W05 evidence. В текущем W05 реальные passing focused checks есть. **REL-02/05/08/11**, Q38.

### I. Review finding binding — текущий blocker подтверждён точно

R05 packet/return однозначно называют `T02-R17`, SHA `ef8da4…`, epoch0 и exact packet hash. Все три findings используют известные criterion/requirement/contract IDs, но не ticket. Поскольку refs известны, append не дополняет ticket, а authorize требует literal membership. AP-P11 воспроизводит этот класс. [E:reviews/review05-packet.json; review05-return.json; state/successor/rev-058-ledger.json#/findings; S:tools/ledger.py:1479–1528,1640–1663,2072–2173.]

Prevention: strict state-bound canonical binding до ingest, не «пусть reviewer всегда вспомнит написать ID». Recovery: новый append-only binding event, который ссылается на неизменённые review packet/return/attempt/subject. Существующий `reported_affected_refs` полезен для сохранения original observation. Нельзя править raw return, повторно ingest отредактированный return, создавать искусственно новый review ради metadata или менять старое source_ref без provenance. **REL-01**.

### J. Устаревший next_action — подтверждён, включая точное значение

В rev58 хранится **`await_blocked_candidate_review`**, а не generic `await_review_return`. Его subject refs всё ещё R05/W05, хотя R05 RETURNED/released и verdict BLOCK уже принят. Code BLOCK branch меняет control/reason/issues, но не action. Обычный PASS path также может оставить await; integrate не имеет общей финальной projection. [E:state/successor/rev-058-ledger.json#/lifecycle; S:tools/ledger.py:1831–1950,2842–2937; AP-P11.]

Вычислять action нужно в общем post-transition reducer и в read-side status из той же verified projection, а не добавлять очередной setter только в текущий BLOCK branch. Action не является разрешением обойти блокер. **REL-06**.

### K. Historical vs actionable findings — хранить 10 нормально, считать все 10 current неправильно

В ledger всего **21 finding**, не 10: 11 старых design findings уже invalidated и 10 T02 change-review findings, у которых invalidated_by пуст. Из последних 7 принадлежат предыдущим candidate reviews, 3 — R05/ef8da4…. При текущем status predicate все 10 выглядят current. Это не corruption immutable history; это неполный currentness/resolution слой. [E:state/successor/rev-058-ledger.json#/findings; S:tools/ledger.py:1706–1723.]

Параллельно есть **17 blocking issues** по условию `impact=blocking && !invalidated_by`: 10 mirrors, 4 verdict issues, W04 scope, W05 external и Review04 termination. `lifecycle.issue_refs` содержит лишь 7 из них, поэтому использовать только этот список как полный перечень active blockers нельзя. Старый first-review mirror тоже потерял ticket binding — это исторический экземпляр incident I, а не только проблема последнего review. [E:state/successor/rev-058-ledger.json#/issues,/lifecycle/issue_refs.]

Нужны два независимых измерения: applicable-to-current-subject и semantic resolution. При новом candidate старый observation становится historical/superseded по subject, **но сам дефект не считается исправленным без proof**. Unresolved obligation должен либо явно carried-forward, либо сопоставлен текущему finding с обоснованием, либо закрыт fresh regression/review evidence. Интеграция использует union обязательных current reviews и unresolved carried obligations. **REL-01/04/06**.

### L. Один finding → одна authorization — свойство текущего schema, не необходимый invariant

`repair_contract` содержит scalar required `finding_ref`; authorization command тоже принимает один `--finding-ref`. Следовательно, current v1.0.11 не выражает один contract с тремя полноценно отслеживаемыми findings. Фактически worker может задеть смежные дефекты, но выдавать это за traced batch repair нельзя. [S:schemas/contracts.schema.json#/$defs/repair_contract; tools/ledger.py:994–1008,2072–2173.]

Безопасный batch возможен: bounded nonempty unique set одного ticket/candidate/intent и, для первого внедрения, одного review; implementation-only scope, при этом causal hypotheses могут различаться; per-finding hypothesis, changed paths, expected proof и stopping condition; одна минимальная union write zone в рамках ticket; одноразовая consumption; новое полное review закрывает каждый finding по отдельности. Нельзя объединять candidate generations, oracle/environment/scope с implementation или автоматически снимать unrelated findings. Singleton compatibility сохраняется. Это **не ослабление traceability**, а устранение случайной serialisation детали. **REL-02**.

## 4. Новые findings и объединённые structural findings

Приоритеты привязаны к текущему проекту: **P0 — до следующего исполнения/интеграции T02; P1 — до T03; P2 — после квалифицированного продолжения.** Несколько симптомов одной причины объединены. Ссылки `AP-Pxx` обозначают мои изолированные проверки, а не исходные тесты проекта.

| ID | Severity | Evidence | Root cause | Failure mode | Recommended change | Tests | Existing-run recovery |
|---|---|---|---|---|---|---|---|
| REL-01 | P0 | E:state/successor/rev-058-ledger.json#/findings,/issues,/reviews; E:reviews/review05-packet.json#/identity,/subject_fingerprint; AP-P11 | Есть immutable return, finding-проекция и отдельный issue-mirror, но ticket/candidate binding и понятие current вычисляются разными командами. append_review_findings добавляет subject только для некоторых сочетаний affected_refs; current означает лишь отсутствие invalidated_by. | Штатный ingest принимает finding с известными criterion/contract refs без ticket; authorize-repair его отвергает. Старые findings остаются подходящими для authorization, а integrate может снять связанные issues значительно шире, чем доказано разрешение findings. Design-currentness migration не является ticket-candidate recovery. | Ввести обязательный context-derived ticket/candidate binding для ticket-scoped review. validate-return до ingest должен либо требовать явный ticket в affected_refs, либо выдавать однозначный canonical binding, который ingest сохранит отдельно от reported refs. Добавить append-only binding-recovery decision и одну active projection для findings, mirrors и verdicts. | Q04, Q11, Q12, Q13, Q30, Q31 | Revision 58 требует специального auditable recovery: связать три R05 findings с T02-R17/ef8da4…, классифицировать семь старых и их mirrors, отдельно разобрать Review04 termination и W04 scope issue. Один prevention patch существующие findings не исправит. |
| REL-02 | P0 | S:tools/ledger.py:994–1032,1134–1426,1953–2043,2072–2173,2261–2351,3147–3241; S:schemas/contracts.schema.json#/$defs/repair_contract; AP-P08; AP-P09; AP-P10; AP-P16 | Repair feasibility распределена по authorize, dispatch, expanded-lease helper, preservation и closure. Часть строгих проверок работает только для create→modify expansion. source_attempt_ref допускает разные типы в разных командах; current_candidate выводится из current_attempt. | Authorize принимает повтор causal signature, dispatch отвергает, READY нельзя штатно заменить. Modify-only repair может идти с чужим base. Source-review разрешён для dispatch, но preservation требует source-worker. После continuation candidate no-change BLOCK repair невозможно закрыть: восстановление требует prior DONE. Batch findings не представимы текущим schema. | Общий validate_repair_plan до READY: точный source candidate, resolved worker source, finding-set currentness, contract bytes, causal novelty, path lineage, denies, scope и stop conditions. Отдельный replace/revoke для любой неиспользованной authorization. Closure использует общий валидатор DONE/continuation candidate, не status==DONE. Хранить current_candidate независимо от latest attempt. | Q02, Q03, Q04, Q10, Q19, Q20, Q27, Q28, Q35, Q38 | R58: current_candidate=W05 continuation; новая authorization только после REL-01 recovery. Для одного worker на три findings нужен новый schema/transition, это невозможно выразить текущим scalar finding_ref. Не восстанавливать current_attempt на W03 и не терять W05 candidate. |
| REL-03 | P0 | S:tools/ledger.py:1831–1855,2842–2937; AP-P03; AP-P12; AP-P13 | ingest-return и integrate — два разных writer-пути для review attempt. Первый запрещает conflicting duplicate; второй заново ingest_payload из mutable inbox даже для RETURNED attempt и не сравнивает digest с сохранённым return_ref. | После настоящего ingest BLOCK изменённый PASS в том же inbox принимается integrate: ticket INTEGRATED, return_ref другой, review_result всё ещё BLOCK, reviews содержат BLOCK и PASS. Даже одинаковый PASS после ingest создаёт ещё одну review record с новым review-id. | Integrate должен потреблять существующий immutable review/qualification ref, не новый return-file. Если совместимый CLI сохраняет review-file, digest обязан совпадать с принятым. Для PREPARED единственный общий atomic ingest path; предпочтительнее отдельный обязательный ingest. Review record создаётся только один раз. | Q01, Q14, Q15, Q26, Q28, Q30 | R58 ещё не integrated, поэтому не имеет доказанной подмены. Сохранить R05 BLOCK и exact return hash, новый PASS только новым review-attempt на новом candidate. Recovery не должен использовать integrate как альтернативный ingest. |
| REL-04 | P0 | S:tools/ledger.py:1434–1463,2655–2705,2842–2937,3728–4011; S:phases/execute.md:7–15; AP-P04 | Qualification частично находится в narrative и более строгом manual-import, но generic review/integrate не используют обязательный единый predicate. PASS проверяет coverage, но не outcomes всех independent checks; integrity receipt допускает отсутствие candidate_fingerprint и ledger_hash. | PASS с check=failed принимается и интегрируется. Ticket risk=critical не требует отдельного независимого critical review: одного routine PASS и {status:PASS} достаточно helper. Active blockers и pending other reviews не агрегируются в integrate; снятие issues по ticket шире proof. Это не означает, что в реальном run barrier был обойдён: Review04 как раз корректно остановлен. | PASS requires every required independent check fulfilled, full exact criteria/axes and no blocking findings. Ввести review requirements от ticket/intent/risk: routine и отдельно qualified critical/manual axis. Обязательная hash-bound post-stop integrity receipt и отсутствие unresolved applicable blockers до integration. Не принимать произвольный status-only receipt. | Q01, Q13, Q18, Q21, Q22, Q28, Q30, Q31, Q36 | R58 routine Review05 прямо не заменяет отдельно требуемую manual critical migration/data-integrity axis. После нового DONE candidate нужны fresh routine + required critical qualification. External fixture blocker W05 не снимается фактом routine PASS. |
| REL-05 | P0 | S:tools/ledger.py:2209–2258,2354–2571,2574–2652,610–649; S:design/lifecycle-model.json#/machines/operation; AP-P01; AP-P02; AP-P14 | Git effect и candidate authority разделены, но отсутствует завершение уже observed/applied effect. Reconcile допускает только prepared; result=unchanged хранит abandoned, а replay сравнивает state с raw command result. | prepared→uncertain создаёт состояние, которое нельзя штатно разрешить. Reconcile commit→applied оставляет candidate null, а candidate/preserve требуют prepared. Повтор unchanged rejected; prepare-effect возвращает abandoned как idempotent prepared без права фактически повторять effect. Crash после ledger commit до snapshot может оставить committed state при ошибке ответа. | Разрешить guarded uncertain→observed applied/abandoned с fresh exact receipt. Candidate finalization должна принимать applied-but-not-published той же операции и атомарно привязывать candidate, не повторяя Git. Нормализовать terminal outcome и operation result для idempotence; abandoned не должен выглядеть ready-to-apply. | Q06, Q19, Q20, Q25, Q26, Q28, Q33 | R58 preservation effect уже applied и candidate опубликован; его не переигрывать. Проверить на будущих T02 repairs; для existing applied/no-candidate runs нужен adoption/finalize transition, а не новый commit. |
| REL-06 | P0 | E:state/successor/rev-058-ledger.json#/lifecycle,/tickets,/attempts; S:tools/ledger.py:346–522,1706–1723,1831–1950,2655–2705,2842–2937; AP-P11 | Каждая команда вручную правит часть агрегированного состояния. Нет общего post-transition invariant и reducer для next_action; он одновременно служит UI подсказкой, инструкцией и косвенным названием gate. | R58 предлагает await_blocked_candidate_review после RETURNED/released review. Обычный PASS тоже оставляет await_review_return. После integrate указатель может оставаться на ожидании. current_attempt скрывает предыдущий candidate, пока новая попытка ещё ничего не произвела. | Детерминированно выводить следующую допустимую action из verified state после каждого mutating command и в status. Добавить invariant: нельзя await terminal producer; current candidate survives failed/no-change attempt; указанные refs существуют и относятся к current subject. | Q01, Q11, Q12, Q15, Q18, Q21, Q24, Q29 | R58 после binding/currentness recovery должен показывать classify/authorize bounded repair (либо exact remaining blocker), а не await Review05. Точное current_candidate ef8da4… сохраняется. |
| REL-07 | P1 | S:tools/ledger.py:1680–1703,1953–2043,2072–2173,2574–2652,2842–2937,4871–5036; S:design/01-lifecycle-state-machine.md (stop, human decisions, successor rules); AP-P06; AP-P07 | transaction проверяет token/revision, но не общую command admissibility. Некоторые команды отдельно защищают terminal states, другие нет. init проверяет другие nonterminal runs под lock конкретного run, а recover может оживить terminal predecessor. | Cancel→QUIESCING не мешает dispatch READY ticket. CANCELLED→recover→RECOVERING проходит вопреки terminal model; после появления successor это может вернуть второго владельца. Проверка двух одновременных init не защищена общим repository lock. Semi checkpoint_policy хранится, но нет универсальной durable dependent-work guard. | Единая таблица разрешённых phase/control/events; terminal запрещает мутации кроме доказанного read-only replay. Recover terminal только explicit new successor flow. Repo-level owner registry/lock для init/takeover/successor. Blocked execution permit только для конкретного approved continuation repair, не blanket unblock. | Q23, Q24, Q29, Q32, Q37, Q39 | Predecessor rev122 не изменять и не recover. До T03 зафиксировать проверяемую границу predecessor evidence и текущего successor. R58 repairs должны разрешаться bounded exception при external blocker, не обходом общего guard. |
| REL-08 | P1 | S:tools/ledger.py:2176–2206,3147–3344,3347–3714,4970–5036; S:phases/recover.md | Одна lease одновременно резервирует product checkout и выражает возможное writer authority. Recovery добавлялся под конкретный returned repair; общей таблицы outcomes (initial/repair × files/no files × stopped/unknown × candidate/no candidate) нет. | No-change initial BLOCK, HANDOFF, FAILED и некоторые LOST/INTERRUPTED не имеют прямого normal retry/closure. Takeover quarantine старой эпохи нельзя освободить terminate-attempt как released; специальная reconciliation не для lost workers. Повтор reconciliation после освобождения recovered lease требует active и отвергается. Returned reviewer release сам по себе не доказывает остановку subprocess. | Разделить producer liveness и checkout reservation. Stop receipt должна связываться с exact run/attempt/epoch/runtime handle. Typed close-nochange/revert-with-proof/adopt-partial transitions для безопасных outcomes; unknown liveness остаётся quarantine. Идемпотентный receipt replay не зависит от более позднего легального освобождения lease. | Q05, Q07, Q09, Q16, Q17, Q18, Q19, Q25, Q32, Q34, Q40 | R58 W05 active lease — допустимая reservation, не автоматическое свидетельство живого worker. Review05 released не заменяет external stop/barrier evidence. Termination issue Review04 должен получить justified superseded resolution после fresh successful review protocol. |
| REL-09 | P1 | S:tools/ledger.py:865–901,1369–1426,1479–1528,1953–2069; AP-P05; AP-P05; AP-P09 | Проверки опираются на конкретный packet, но не всегда на обязательные authoritative ticket/contract/criteria bindings. Deny проверяется только в ветке expanded repair. Worker return identity не сверяет ticket_id и supplied kind с registered attempt kind. | Один path одновременно allow и deny всё равно получает lease и принимается ingest. Worker DONE с чужим ticket_id принимается. Изменённый/укороченный packet критериев может проверяться относительно самого себя, не полного ticket mandate. Stale intent поля необязательны, и dispatch не повторяет весь readiness proof. | validate_execution_binding: exact kind/run/ticket/attempt/epoch/intent/design/base, required criterion/input-contract coverage and deny precedence для всех paths. Авторизованные scoped repair criteria допускаются только explicit plan, не тихим сокращением acceptance. | Q10, Q11, Q14, Q17, Q27, Q35, Q41 | Не обнаружено evidence, что текущий W05 использовал чужой ticket или deny bypass. Проверить bindings fresh repair перед dispatch; существующий run не переписывать по одному synthetic probe. |
| REL-10 | P0 | S:tools/ledger.py:790–892,1953–2069,4668–4805,4871–4966; S:tests/test_design_publication.py (self-produced and external-inactive tests) | Новый publication/G2/G3 guard запрещает любое пересечение input и producer, включая active contracts, но legacy EXECUTE run продолжает мутировать без явной semantic migration. Дополнительно status active не разделяет принятую спецификацию и доступность реализации. | В R58 у current publication найдено 13 пересечений input/producer, включая T02-R17→CT-V2-ARCHITECTURE-R17 и T03-R17→CT-V2-ARCHITECTURE-R17/CT-V2-RUNTIME-R17. Pure validate_ticket_contract_bindings отвергает эти реальные поля. Все contracts active: это не буквальное повторение прежнего proposed readiness failure, но рассогласование legacy bundle с текущим G2/G3 invariant. Внешний proposed input также может оставаться late blocker без defined activation path. | До нового T02 dispatch выполнить явную compatibility assessment 13 bindings и owner-authorized normalization только если доказана неизменность продуктового смысла; сохранить frozen publication bytes. Если смысл меняется, нужен versioned replan, а не ручное удаление refs. На G2/G3 проверять accepted spec и implementation availability/dependencies; не auto-activate proposed outputs. | Q01, Q23, Q24, Q37, Q42 | R58 требует дополнительного recovery/compatibility decision для 13 active self-produced intersections. Исходные canonical product documents не включены: какой ref является настоящим input, нельзя решить по одному producer list. Same-run continuation допустим только после доказанной metadata-only normalization; иначе нужен явный versioned replan/successor. Predecessor rev120/122 не менять. |
| REL-11 | P1 | S:tools/ledger.py:652–664,895–901,2209–2258,2595–2652,2983–3144; S:phases/execute.md:9–14 | Content-addressed objects создаются с digest, но stored_payload читает путь без повторной проверки digest. Обычный candidate допускает status-only claims с SHA/tree, меняет operation target/authority из receipt и не требует полного persisted write-set audit; preservation заметно строже. | Повреждённый object file может быть принят под старым digest при subsequent semantic checks. Нет machine-enforced обязательности actual audit, exact target/base/authority/parent и hash-bound receipt для обычного DONE candidate. Это слабость проверки receipts, не доказанный факт повреждения текущего run. | Проверять filename digest при каждом immutable-object read. Receipt schemas с mandatory identity/base/target/tree/authority/audit hashes. Один candidate finalizer для DONE и continuation с разной eligibility, но одинаковыми evidence checks. Не заменять исходные effect target/authority полями receipt. | Q06, Q09, Q10, Q25, Q26, Q33, Q36, Q41 | Проверенные packet hashes подтверждают целостность предоставленного evidence, но не весь отсутствующий original object store/checkout. R58 требует live exact Git/barrier verification перед reuse; raw evidence не менять. |
| REL-12 | P1 | S:tests/test_state_machine_model.py; S:tests/test_continuation_candidates.py:156–246 | Graph tests проверяют описательную модель, не исполнения CLI edges. Многие regression fixtures напрямую seed state и заканчиваются на dispatch или recovery, не на fresh review/integration. Выполняемые qualification scripts/часть runtime modules не включены в архив. | Model graph проходит при реальном impossible uncertain→resolved. Existing continuation happy test останавливается после первого repair dispatch. Полный пакет запускает 80 entries: 71 pass, 1 skip, 6 errors+2 failures из-за missing files. Заявленные release qualification результаты нельзя независимо повторить по архиву. | Отдельный reproducible lifecycle qualification package: real Git, deterministic fake runtime, public CLI only after bootstrap, full success and negative chains, fault injection after every durable boundary. Включить все зависимости и env manifest; source packet completeness test отдельно от software defects. | Q01, Q02, Q03, Q04, Q05, Q06, Q07, Q08, Q09, Q10, Q11, Q12, Q13, Q14, Q15, Q16, Q17, Q18, Q19, Q20, Q21, Q22, Q23, Q24, Q25, Q26, Q27, Q28, Q29, Q30, Q31, Q32, Q33, Q34, Q35, Q36, Q37, Q38, Q39, Q40, Q41, Q42 | R58 packet can be regression fixture but needs materialized matching objects/runtime paths in test copy; do not change original paths/history in user run. Missing application checkout means no independent re-run of product regression findings. |
| REL-13 | P2 | S:tools/ledger.py (5123 lines); S:design/lifecycle-model.json | Domain validation, CLI, projections, durable storage, Git proof inspection и migrations находятся в одном модуле с прямыми state mutations. | Новые narrow recovery patches легко добавляют preconditions, которые соседние команды не разделяют; локальные тесты не гарантируют согласованность. | Сначала выделять pure validators/reducers без смены CLI и storage layout; не начинать с полного rewrite. | Q01, Q03, Q25, Q28 | Отдельного recovery сверх P0/P1 не требуется. |
| REL-14 | P2 | S:tools/ledger.py:1953–2043,2655–2705; S:references/ledger.md:99 | Helper регистрирует PREPARED и сразу увеличивает spawn_calls, но не владеет spawn/wait turn и не хранит полноценный runtime receipt/handle state. | Dispatch record не различает worker не был запущен, ещё работает, потерян handle или ответ готов в inbox. Один prompt не гарантирует, что host продолжит ждать без user message. | Добавить optional native-start/stop/return-observed receipts, instance ID, heartbeat observations и раздельные registration/spawn counters. Unknown остаётся unknown; не фабриковать DISPATCHED. | Q16, Q17, Q18, Q25, Q32 | R58 не требует восстановить старые UI handles; exact inbox/receipt/stop verification достаточны при безопасной reuse qualification. |

### Как читать степень доказанности
`evidence_confirmed` — состояние непосредственно видно в frozen artifacts; `reproduced` — наблюдение повторено на изолированной fixture исходным helper; `static_confirmed` — конкретный predicate/отсутствующий вызов проверен в коде; `design_recommendation` — предлагаемое изменение, не существующая возможность. Они не означают, что был перебран весь state space.

## 5. Structural root-cause analysis

### 5.1. Реляционные связи существуют, но не являются общими invariants

Почти все повторяющиеся incidents — не отсутствие очередного `if`, а отсутствие **общего определения identity и applicability**. На одном переходе достаточно known ref, на другом ticket ref; provenance строгая только для expanded path; publication запрещает input/output intersection, но continuing legacy EXECUTE этого не перепроверяет; review fingerprint сверяется с registered attempt, а integration дополнительно с current worker, но не со всей required-review set. Поэтому accepted input одного transition оказывается unusable input следующего.

Предлагаемый общий proof context:

```text
run_id + epoch + intent_revision + effective_design_binding
+ ticket_id + candidate_id/SHA + explicit parent candidate
+ bounded finding IDs + required review mandates
+ authorization identity/hash + exact write zone/denies
+ stopped producer / reservation proof + verified effect/receipt identity
```

Его следует строить один раз общим validator, а downstream команды должны использовать те же canonical значения. Повторно проверить changed environment перед effect необходимо, но **семантика** проверки не должна отличаться.

### 5.2. History, live work и current subject нужно разделить

Не требуется полноценная новая event-sourcing платформа. Достаточно сохранить существующие arrays и content-addressed store, добавить explicit event/decision records и нормализованные projections:

| Область | Immutable evidence | Mutable/derived current projection |
|---|---|---|
| Attempt | packet, return, runtime observations | live/latest attempt; terminal result; liveness unknown/stopped |
| Candidate | SHA/tree/base, parent ref, audit/receipt, origin attempt | ticket.current_candidate; kind DONE-qualified/continuation-only; current/superseded |
| Finding | original claim/refs/source return | canonical context binding; subject applicability; semantic disposition; carry-forward obligation |
| Authorization | exact requested repair plan + owner decision | authorized/consumed/revoked/superseded; single consuming attempt |
| Review | exact packet/return/receipt and reviewer identity | qualification against required current mandates; not last return wins |
| Lease | grant/release/quarantine/stop observations | writer authority and candidate reservation as different facts |
| Action | event outcome and reason history | deterministic next legal action, required proof, human_input_required |

`current_attempt` может остаться для backwards-compatible display, но не должен служить единственным адресом candidate. Новый candidate graph хранит parent ID, не только base SHA: no-op candidates с одинаковым SHA не обязательно являются fork. Вместе с тем произвольный выбор одного parent из нескольких — недопустим.

### 5.3. Общий transition layer без переписывания CLI

```text
current verified state + typed event
    → validate authority / phase / identity / expected revision
    → resolve canonical proof context
    → validate event preconditions
    → construct next state in memory
    → validate cross-entity invariants
    → derive current projections / next_action
    → atomic publish with immutable event/receipt references
    → return stable semantic operation result
```

Начать с существующих `cmd_*` как adapters. Вынести pure функции для review binding, repair feasibility, candidate lineage, operation finalization и integration qualification; затем общий reducer и phase/control table. Git и model calls по-прежнему вне helper. Event names и guards должны быть явными: не определять G2/G3 по подстроке в `next_action`.

Минимальные cross-state invariants: current pointers существуют и subject-compatible; at most one product writer owns overlapping zone; terminal attempts не ждутся как live; no stale or foreign return; continuation cannot integrate; all required reviews current/qualified; no unresolved applicable finding or uncertain effect at integration; consumed authorization immutable for historical provenance; every nonterminal exceptional state has a safe legal action or explicit external proof requirement. Safety blocker с понятным external action допустим; «reconcile_uncertain» при отсутствии применимой команды — lifecycle dead end.

### 5.4. Idempotence должна проверять завершённый event, а не случайную промежуточную форму state

Сегодня `ingest` хорошо проверяет exact bytes; `prepare-review`, authorization и termination часто не adopt-ят уже совершённый переход; reconciliation требует промежуточную active lease; closure требует всё ещё restored current pointer. Это делает retry зависимым от времени и последующих legitimate transitions.

Нужны `event_id + semantic_input_hash + stored_result`, проверка current owner/authority, а затем stable replay результата. **Не сравнивать без необходимости весь current ledger с post-state старого event:** он законно мог продвинуться. Conflict same ID/different inputs должен fail closed. Old event replay не может вернуть утраченную lease, оживить terminal attempt или сменить candidate. Commands с повторным внешним эффектом должны ссылаться на исходный effect ID; новые IDs не являются способом обойти uncertain state.

### 5.5. Схема миграции и rollback runtime

Current schema version `1.0` и creation `skill_version` сами по себе недостаточны для нового semantics. У R58 `creation_skill_version=1.0.5`, `last_mutating_skill_version=1.0.11`; это не означает автоматическое соответствие всем новым guards. Новая semantic migration должна содержать source snapshot hash, target schema/compatibility floor, selected events, derived bindings, unresolved items и owner authorization. Старый runtime не должен иметь write access к migrated state без понимания новых records.

Миграция сначала вычисляет proposed state read-only на копии, затем whole invariants и qualification, потом одна auditable publication либо явный отказ. Исправить только durable view допустимо, когда raw observations остаются истинными и смысл не меняется. Unknown bindings/proofs должны оставаться unknown. Для contract semantics или scope changes нужен versioned design/intent путь; не маскировать его «technical migration».

## 6. P0 / P1 / P2 improvement plan

### Зависимости и порядок
Сначала зафиксировать baseline и failing regression cases. REL-10 требует отдельной compatibility assessment current R58 bindings до восстановления dispatch. REL-01/02/06 образуют единый repair-state пакет; REL-03/04 — единый review/integration пакет; REL-05 — effect completion. Все семь P0 должны пройти целевой continuation→repair→review→integrate сценарий до возвращения в T02. P1 расширяют тот же слой на отмену, takeover, scope и длинный multi-ticket run. Не выпускать новую recovery-команду без проверки её непосредственного следующего перехода.

### REL-01 · P0 — Finding binding, currentness и issue-mirrors не имеют единого lifecycle

**Причина.** Есть immutable return, finding-проекция и отдельный issue-mirror, но ticket/candidate binding и понятие current вычисляются разными командами. append_review_findings добавляет subject только для некоторых сочетаний affected_refs; current означает лишь отсутствие invalidated_by.

**Affected files / evidence.** E:state/successor/rev-058-ledger.json#/findings,/issues,/reviews; E:reviews/review05-packet.json#/identity,/subject_fingerprint; E:reviews/review05-return.json#/findings; S:tools/ledger.py:1479–1528,1640–1663,1706–1723,2072–2173,2905–2933,4373–4652; AP-P11

**Минимальное безопасное изменение.** Ввести обязательный context-derived ticket/candidate binding для ticket-scoped review. validate-return до ingest должен либо требовать явный ticket в affected_refs, либо выдавать однозначный canonical binding, который ingest сохранит отдельно от reported refs. Добавить append-only binding-recovery decision и одну active projection для findings, mirrors и verdicts.

**Системное изменение.** Разделить immutable observation, binding decision, subject_currentness и semantic_resolution. Superseded subject не равен resolved defect. Хранить unresolved carry-forward obligations; все consumers используют один projection. Несколько обязательных reviews одного candidate объединяются, а не заменяют друг друга последним verdict.

**Regression tests.** Known criterion-only refs: reject before publication or canonical binding; packet subject never inferred from arbitrary global ref; Recovery three R58 findings leaves original return hashes and reported refs unchanged; ambiguous context rejects; Seven historical ticket findings + 11 design findings distinguish from current three; Resolving one finding changes only justified mirror/verdict obligations; active unrelated finding remains blocking; Replay recovery after further legitimate transitions remains no-op

**Qualification cases.** Q04; Q11; Q12; Q13; Q30; Q31

**Backward compatibility.** Читать старые affected_refs как reported evidence. Новый binding/resolution overlay добавляется версионированной миграцией. Не переписывать старые objects и не заполнять неизвестные candidate refs догадкой.

**Existing-run recovery.** Revision 58 требует специального auditable recovery: связать три R05 findings с T02-R17/ef8da4…, классифицировать семь старых и их mirrors, отдельно разобрать Review04 termination и W04 scope issue. Один prevention patch существующие findings не исправит.

**Граница реализации.** Полностью внутри Autopilot; смысловая проверка связи старых findings требует owner/reviewer evidence, не произвольного auto-resolve.

**Acceptance criteria.** Невозможно ingest ticket-scoped blocking finding, который следующий authorize не может адресовать из-за binding; status, authorize, integrate и G4 видят одну active projection; Исторические обязательства не исчезают без explicit disposition/evidence

### REL-02 · P0 — Authorization и continuation используют несовместимые repair/provenance preconditions

**Причина.** Repair feasibility распределена по authorize, dispatch, expanded-lease helper, preservation и closure. Часть строгих проверок работает только для create→modify expansion. source_attempt_ref допускает разные типы в разных командах; current_candidate выводится из current_attempt.

**Affected files / evidence.** S:tools/ledger.py:994–1032,1134–1426,1953–2043,2072–2173,2261–2351,3147–3241; S:schemas/contracts.schema.json#/$defs/repair_contract; E:authorizations/repair-auth-05-defective-contract.json; E:authorizations/repair-auth-06-rebound-contract.json; AP-P08; AP-P09; AP-P10; AP-P16

**Минимальное безопасное изменение.** Общий validate_repair_plan до READY: точный source candidate, resolved worker source, finding-set currentness, contract bytes, causal novelty, path lineage, denies, scope и stop conditions. Отдельный replace/revoke для любой неиспользованной authorization. Closure использует общий валидатор DONE/continuation candidate, не status==DONE. Хранить current_candidate независимо от latest attempt.

**Системное изменение.** RepairPlan с bounded finding_refs[] одного ticket/review/candidate и per-finding proof map. Старый finding_ref нормализовать в singleton. Один authorized plan потребляется ровно одной попыткой; новые repairs получают новый план, но исторические consumed-authorizations остаются пригодными для проверки lineage. Не инвалидировать происхождение старого candidate при обычном закрытии finding.

**Regression tests.** Authorize→dispatch accepts all legitimate source-worker/source-review variants and rejects same invalid input before READY; Ordinary modify wrong base and stale finding reject, not only create expansion; Unused authorization replace/revoke/idempotent retry; consumed replacement forbidden; Continuation→repair BLOCK files=[] restores prior continuation using receipt; initial no-candidate outcome routed separately; Repair touching another file preserves path-specific origin; ambiguous same-SHA/fork and cycles reject; Batch three findings exactly same source and candidate, per-finding regressions; cross-ticket/candidate set rejects

**Qualification cases.** Q02; Q03; Q04; Q10; Q19; Q20; Q27; Q28; Q35; Q38

**Backward compatibility.** Сохранить legacy singleton контракт. Нормализованный source-worker и current_candidate выводить только из уникальной доказанной цепи; неоднозначность блокирует миграцию. New schema must not be silently writable by old runtime.

**Existing-run recovery.** R58: current_candidate=W05 continuation; новая authorization только после REL-01 recovery. Для одного worker на три findings нужен новый schema/transition, это невозможно выразить текущим scalar finding_ref. Не восстанавливать current_attempt на W03 и не терять W05 candidate.

**Граница реализации.** Внутри Autopilot, кроме доказательства остановки исполнителей и фактического состояния checkout.

**Acceptance criteria.** Accepted authorization is dispatchable unless a recorded intervening event made it stale; No-change repair after continuation has an auditable bounded exit; Authorization lifecycle is authorized→consumed OR revoked/superseded, with exact replay semantics

### REL-03 · P0 — Integrate обходит immutable ingest и может заменить принятый BLOCK другим PASS

**Причина.** ingest-return и integrate — два разных writer-пути для review attempt. Первый запрещает conflicting duplicate; второй заново ingest_payload из mutable inbox даже для RETURNED attempt и не сравнивает digest с сохранённым return_ref.

**Affected files / evidence.** S:tools/ledger.py:1831–1855,2842–2937; AP-P03; AP-P12; AP-P13

**Минимальное безопасное изменение.** Integrate должен потреблять существующий immutable review/qualification ref, не новый return-file. Если совместимый CLI сохраняет review-file, digest обязан совпадать с принятым. Для PREPARED единственный общий atomic ingest path; предпочтительнее отдельный обязательный ingest. Review record создаётся только один раз.

**Системное изменение.** Один event ReviewReturned с unique key attempt_id+return_hash, один aggregate verdict и отдельный event CandidateIntegrated. Integration никогда не меняет review payload, finding_refs или verdict. Replay возвращает исходный operation result после проверки owner и intent/candidate identity.

**Regression tests.** Ingest BLOCK then replace exact inbox bytes with PASS: integrate must reject, ledger bytes unchanged; Same PASS ingest→integrate retains one review record; return_ref and review_result identical; Conflicting duplicate through every public entry point rejects; Replay integrate with original stale revision after successful commit is same result, not duplicate revision

**Qualification cases.** Q01; Q14; Q15; Q26; Q28; Q30

**Backward compatibility.** Существующие returned reviews остаются неизменными. Старые integrated records проверить на conflicting return hashes; не объявлять их валидными автоматически.

**Existing-run recovery.** R58 ещё не integrated, поэтому не имеет доказанной подмены. Сохранить R05 BLOCK и exact return hash, новый PASS только новым review-attempt на новом candidate. Recovery не должен использовать integrate как альтернативный ingest.

**Граница реализации.** Полностью внутри Autopilot.

**Acceptance criteria.** No API can change immutable return_ref of a terminal RETURNED attempt; INTEGRATED requires one consistent authoritative review result; Duplicate returns and integrations are zero-effect

### REL-04 · P0 — PASS и integration не обеспечивают требуемую review qualification и critical barrier

**Причина.** Qualification частично находится в narrative и более строгом manual-import, но generic review/integrate не используют обязательный единый predicate. PASS проверяет coverage, но не outcomes всех independent checks; integrity receipt допускает отсутствие candidate_fingerprint и ledger_hash.

**Affected files / evidence.** S:tools/ledger.py:1434–1463,2655–2705,2842–2937,3728–4011; S:phases/execute.md:7–15; E:reviews/review05-packet.json#/mandate,/axes; E:reviews/review04-termination-receipt.json; AP-P04

**Минимальное безопасное изменение.** PASS requires every required independent check fulfilled, full exact criteria/axes and no blocking findings. Ввести review requirements от ticket/intent/risk: routine и отдельно qualified critical/manual axis. Обязательная hash-bound post-stop integrity receipt и отсутствие unresolved applicable blockers до integration. Не принимать произвольный status-only receipt.

**Системное изменение.** ReviewQualification aggregate: subject, required mandates, independent identities/routes, isolation receipt, stop receipt, post-review integrity, exact result hashes и finding dispositions. Одинаковый validator для ingest, manual import, integration, G4/G5/G6. Дополнительный manual critical review не подменять количеством осей в routine return.

**Regression tests.** PASS with failed/not_run/unverifiable required check rejects before publication; Critical routine-only PASS cannot integrate; separate current critical axis required; Receipt missing subject/hash/stop/export bindings rejects; contaminated export invalidates review and keeps safe lease state; Two current reviewers BLOCK/PASS require evidence adjudication, not last writer wins; Unrelated external blocker and unresolved historical obligation prevent completion, not broad issue clearing

**Qualification cases.** Q01; Q13; Q18; Q21; Q22; Q28; Q30; Q31; Q36

**Backward compatibility.** Не приписывать отсутствующие stop/integrity proofs старым reviews. Legacy qualified receipts may be adopted only by explicit verified recovery; otherwise re-review exact candidate.

**Existing-run recovery.** R58 routine Review05 прямо не заменяет отдельно требуемую manual critical migration/data-integrity axis. После нового DONE candidate нужны fresh routine + required critical qualification. External fixture blocker W05 не снимается фактом routine PASS.

**Граница реализации.** Guards и receipts — внутри Autopilot; реальная изоляция, остановка дочерних процессов и независимый transport зависят от runtime/оператора.

**Acceptance criteria.** A schema-valid but semantically contradictory PASS cannot qualify; Current T02 cannot integrate without its separately required critical axis; No integration while relevant unresolved blockers/reviews/effects remain

### REL-05 · P0 — Effect reconciliation не замыкается в candidate publication и не является retry-safe

**Причина.** Git effect и candidate authority разделены, но отсутствует завершение уже observed/applied effect. Reconcile допускает только prepared; result=unchanged хранит abandoned, а replay сравнивает state с raw command result.

**Affected files / evidence.** S:tools/ledger.py:2209–2258,2354–2571,2574–2652,610–649; S:design/lifecycle-model.json#/machines/operation; AP-P01; AP-P02; AP-P14

**Минимальное безопасное изменение.** Разрешить guarded uncertain→observed applied/abandoned с fresh exact receipt. Candidate finalization должна принимать applied-but-not-published той же операции и атомарно привязывать candidate, не повторяя Git. Нормализовать terminal outcome и operation result для idempotence; abandoned не должен выглядеть ready-to-apply.

**Системное изменение.** Effect lifecycle prepared→observed→finalized либо uncertain→resolution. Unique effect ID и semantic request fingerprint; один immutable receipt связывает run/ticket/attempt/base/tree/target/authority. Отдельная safe resume action после каждого durable step. Сохранять pending adoption вместо переименования операции и повторного commit.

**Regression tests.** Real Git commit → reconcile applied → ordinary candidate/preserve succeeds once without second commit; uncertain→applied/unchanged evidence retry; conflicting receipt fails; Exact replay unchanged after success is no-op even though stored state abandoned; Inject crash after each atomic_write/object_store/Git/receipt/finalization; state recovers to old or next complete transition; Wrong checkout/base/tree/authority receipt rejected before ledger publication

**Qualification cases.** Q06; Q19; Q20; Q25; Q26; Q28; Q33

**Backward compatibility.** Prepared/applied legacy operations must be classified from exact Git and stored receipts. Cannot infer absence of effect from missing response; unresolved evidence stays uncertain.

**Existing-run recovery.** R58 preservation effect уже applied и candidate опубликован; его не переигрывать. Проверить на будущих T02 repairs; для existing applied/no-candidate runs нужен adoption/finalize transition, а не новый commit.

**Граница реализации.** State/recovery logic — внутри Autopilot; Git side effect и достоверность runtime stop/receipt — внешняя approved boundary.

**Acceptance criteria.** Every recorded effect state has a safe next action; No recovery command requires repeating an already observed commit; Exact successful retry never creates a duplicate candidate or revision

### REL-06 · P0 — next_action и ticket/candidate/current projections обновляются частично

**Причина.** Каждая команда вручную правит часть агрегированного состояния. Нет общего post-transition invariant и reducer для next_action; он одновременно служит UI подсказкой, инструкцией и косвенным названием gate.

**Affected files / evidence.** E:state/successor/rev-058-ledger.json#/lifecycle,/tickets,/attempts; S:tools/ledger.py:346–522,1706–1723,1831–1950,2655–2705,2842–2937; AP-P11

**Минимальное безопасное изменение.** Детерминированно выводить следующую допустимую action из verified state после каждого mutating command и в status. Добавить invariant: нельзя await terminal producer; current candidate survives failed/no-change attempt; указанные refs существуют и относятся к current subject.

**Системное изменение.** Typed next_action(kind, subject, blockers, required_evidence, human_input_required) как projection, а не право менять state. Event→validate→apply→validate_invariants→derive_views→publish. CLI gate должен принимать explicit event/gate ID, не угадывать guard из текста next_action.

**Regression tests.** Review BLOCK/PASS/UNVERIFIABLE and integrate all derive correct next action; No await for RETURNED/LOST/INTERRUPTED; no dispatch when only unresolved human checkpoint is legal; Recover/status compute same current findings/candidate as mutating commands; Multiple required reviews: await only outstanding live review, not the finished one

**Qualification cases.** Q01; Q11; Q12; Q15; Q18; Q21; Q24; Q29

**Backward compatibility.** Старые next_action сохранять как historical observation, но current projection пересчитывать. Не считать одну новую строку next_action самостоятельным разрешением repair или integration.

**Existing-run recovery.** R58 после binding/currentness recovery должен показывать classify/authorize bounded repair (либо exact remaining blocker), а не await Review05. Точное current_candidate ef8da4… сохраняется.

**Граница реализации.** Внутри Autopilot; renderer может подсказать действие, но не может заставить внешний runtime продолжить turn.

**Acceptance criteria.** Every published aggregate passes cross-field consistency; Status never advises an impossible next command; Projection-only rebuild preserves immutable evidence and verdicts

### REL-07 · P1 — Run/control guards, terminal immutability и successor ownership не унифицированы

**Причина.** transaction проверяет token/revision, но не общую command admissibility. Некоторые команды отдельно защищают terminal states, другие нет. init проверяет другие nonterminal runs под lock конкретного run, а recover может оживить terminal predecessor.

**Affected files / evidence.** S:tools/ledger.py:1680–1703,1953–2043,2072–2173,2574–2652,2842–2937,4871–5036; S:design/01-lifecycle-state-machine.md (stop, human decisions, successor rules); AP-P06; AP-P07

**Минимальное безопасное изменение.** Единая таблица разрешённых phase/control/events; terminal запрещает мутации кроме доказанного read-only replay. Recover terminal только explicit new successor flow. Repo-level owner registry/lock для init/takeover/successor. Blocked execution permit только для конкретного approved continuation repair, не blanket unblock.

**Системное изменение.** Durable successor handoff: predecessor terminal hash, stop/effect receipts, accepted inheritance refs, checkout/base and no predecessor authority transfer. Explicit checkpoint pending/answered events для реально требуемых user decisions; не вводить подтверждение каждого ticket/wave в semi.

**Regression tests.** QUIESCING/PAUSED/terminal deny fresh dispatch/effect/authorization/integration; Terminal recover cannot resurrect predecessor after successor owns repo; Concurrent init attempts under same control root produce exactly one owner; Semi routine dispatch proceeds; pending scope/irreversible/intent checkpoint blocks only dependent work; Successor imports accepted evidence and mapping, not live leases/auths/current pointers

**Qualification cases.** Q23; Q24; Q29; Q32; Q37; Q39

**Backward compatibility.** Валидные terminal runs остаются terminal. Legacy successor identity/evidence без явного handoff нельзя автоматически считать доказанным; нужен explicit registration receipt.

**Existing-run recovery.** Predecessor rev122 не изменять и не recover. До T03 зафиксировать проверяемую границу predecessor evidence и текущего successor. R58 repairs должны разрешаться bounded exception при external blocker, не обходом общего guard.

**Граница реализации.** Внутри Autopilot для ownership/protocol; native approval и human decision остаются внешними источниками authority.

**Acceptance criteria.** No side-effect-producing event is legal during quiesce/terminal; One repository has one authorized nonterminal owner; Human checkpoints are explicit and distinct from routine internal waits

### REL-08 · P1 — Lease/liveness и recovery покрывают узкие исключения, но не полный набор остановок

**Причина.** Одна lease одновременно резервирует product checkout и выражает возможное writer authority. Recovery добавлялся под конкретный returned repair; общей таблицы outcomes (initial/repair × files/no files × stopped/unknown × candidate/no candidate) нет.

**Affected files / evidence.** S:tools/ledger.py:2176–2206,3147–3344,3347–3714,4970–5036; S:phases/recover.md; E:reviews/review04-termination-receipt.json; E:state/successor/rev-056-review04-terminated.json

**Минимальное безопасное изменение.** Разделить producer liveness и checkout reservation. Stop receipt должна связываться с exact run/attempt/epoch/runtime handle. Typed close-nochange/revert-with-proof/adopt-partial transitions для безопасных outcomes; unknown liveness остаётся quarantine. Идемпотентный receipt replay не зависит от более позднего легального освобождения lease.

**Системное изменение.** Recovery dispatcher выбирает documented bounded path по verified effects/candidate/ownership, не по номеру прошлого incident. Потеря handle допускает corroborated attestation route, но не выдаёт runtime-proof. Generic quarantine reconciliation не означает auto-release.

**Regression tests.** Full closure truth table, including initial BLOCK no files, HANDOFF no files, FAILED, lost worker before/after writes; Old-epoch stopped attempt releases only through takeover reconciliation with exact proof; Repeat legacy reconciliation after candidate reviewed/integrated is no-op; Return accepted but process still alive cannot qualify integrity/reuse barrier; Safe revert never modifies foreign paths and retains pre/post fingerprints

**Qualification cases.** Q05; Q07; Q09; Q16; Q17; Q18; Q19; Q25; Q32; Q34; Q40

**Backward compatibility.** Не интерпретировать legacy lease=active как доказательство живого процесса и released как доказательство verified clean checkout. Новые liveness поля unknown до квалифицированного наблюдения.

**Existing-run recovery.** R58 W05 active lease — допустимая reservation, не автоматическое свидетельство живого worker. Review05 released не заменяет external stop/barrier evidence. Termination issue Review04 должен получить justified superseded resolution после fresh successful review protocol.

**Граница реализации.** Протокол внутри Autopilot; истинное завершение процессов/дочерних инструментов зависит от внешнего runtime.

**Acceptance criteria.** Each safe terminal attempt outcome has documented continuation or explicit bounded blocker; No timeout-only or token-only lease release; Recovery replay does not break after normal downstream progress

### REL-09 · P1 — Packet/return scope и identity проверяются не одинаково на всех путях

**Причина.** Проверки опираются на конкретный packet, но не всегда на обязательные authoritative ticket/contract/criteria bindings. Deny проверяется только в ветке expanded repair. Worker return identity не сверяет ticket_id и supplied kind с registered attempt kind.

**Affected files / evidence.** S:tools/ledger.py:865–901,1369–1426,1479–1528,1953–2069; AP-P05; AP-P09

**Минимальное безопасное изменение.** validate_execution_binding: exact kind/run/ticket/attempt/epoch/intent/design/base, required criterion/input-contract coverage and deny precedence для всех paths. Авторизованные scoped repair criteria допускаются только explicit plan, не тихим сокращением acceptance.

**Системное изменение.** Общий ExecutionContext с immutable binding fingerprint используется prepare/dispatch/validate-return/ingest/audit/candidate. Readiness receipt привязать к dependency/invalidation versions, но revalidate на dispatch если окружение изменилось.

**Regression tests.** allow∩deny reject for implement and ordinary repair, not only expansion; Wrong return ticket/kind reject without ledger publication; Omitted/stale intent or contract binding cannot bypass current mandate in current-schema packets; Narrow repair packet remains traceable to full ticket and final whole-ticket review; Blocked ticket with active lease cannot be hidden by ticket status when another writer is dispatched

**Qualification cases.** Q10; Q11; Q14; Q17; Q27; Q35; Q41

**Backward compatibility.** Legacy packets не объявлять автоматически scope-complete. Для действующих attempts exact historical packet сохраняется; дополнительное acceptance/recovery binding только с explicit evidence.

**Existing-run recovery.** Не обнаружено evidence, что текущий W05 использовал чужой ticket или deny bypass. Проверить bindings fresh repair перед dispatch; существующий run не переписывать по одному synthetic probe.

**Граница реализации.** Внутри Autopilot; обнаружение фактических filesystem effects требует audit/runtime observations.

**Acceptance criteria.** No accepted return changes subject identity; Deny always dominates allow; All accepted packet reductions have explicit authority

### REL-10 · P0 — Legacy current bundle не проходит новый input/output invariant; readiness planning неполон

**Причина.** Новый publication/G2/G3 guard запрещает любое пересечение input и producer, включая active contracts, но legacy EXECUTE run продолжает мутировать без явной semantic migration. Дополнительно status active не разделяет принятую спецификацию и доступность реализации.

**Affected files / evidence.** S:tools/ledger.py:790–892,1953–2069,4668–4805,4871–4966; S:tests/test_design_publication.py (self-produced and external-inactive tests); audit-evidence/revision58-binding-revalidation.json; E:state/predecessor/rev-120-readiness-blocked.json; E:state/successor/rev-058-ledger.json#/contracts,/design_publication

**Минимальное безопасное изменение.** До нового T02 dispatch выполнить явную compatibility assessment 13 bindings и owner-authorized normalization только если доказана неизменность продуктового смысла; сохранить frozen publication bytes. Если смысл меняется, нужен versioned replan, а не ручное удаление refs. На G2/G3 проверять accepted spec и implementation availability/dependencies; не auto-activate proposed outputs.

**Системное изменение.** Разделить specification_status и implementation_availability. Validate readiness dependency closure заранее, при этом runtime environment inputs с неизвестной доступностью остаются явным planned blocker, а не скрытым дефектом bundle.

**Regression tests.** Producer→consumer pair with proposed input either rejected early or has tested activation path; Active spec without producer integrated cannot authorize consumer when it needs implementation; Self-produced input rejects publication and G2/G3 for legacy bundles; Imported predecessor contract requires source evidence and exact version mapping

**Qualification cases.** Q01; Q23; Q24; Q37; Q42

**Backward compatibility.** Не переинтерпретировать старые active/proposed молча. Сохранить statuses; новый readiness manifest объясняет, что именно доступно.

**Existing-run recovery.** R58 требует дополнительного recovery/compatibility decision для 13 active self-produced intersections. Исходные canonical product documents не включены: какой ref является настоящим input, нельзя решить по одному producer list. Same-run continuation допустим только после доказанной metadata-only normalization; иначе нужен явный versioned replan/successor. Predecessor rev120/122 не менять.

**Граница реализации.** Внутри Autopilot для planning; реальная доступность внешнего input определяется evidence/preflight.

**Acceptance criteria.** Pure binding validator accepts the explicitly migrated effective R58 view without rewriting original publication; G3 cannot approve a statically impossible producer-consumer chain; A contract status alone never stands in for dependency completion

### REL-11 · P1 — Evidence store и обычная candidate publication слабее заявленного proof boundary

**Причина.** Content-addressed objects создаются с digest, но stored_payload читает путь без повторной проверки digest. Обычный candidate допускает status-only claims с SHA/tree, меняет operation target/authority из receipt и не требует полного persisted write-set audit; preservation заметно строже.

**Affected files / evidence.** S:tools/ledger.py:652–664,895–901,2209–2258,2595–2652,2983–3144; S:phases/execute.md:9–14; E:receipts/worker05-continuation-receipt.json

**Минимальное безопасное изменение.** Проверять filename digest при каждом immutable-object read. Receipt schemas с mandatory identity/base/target/tree/authority/audit hashes. Один candidate finalizer для DONE и continuation с разной eligibility, но одинаковыми evidence checks. Не заменять исходные effect target/authority полями receipt.

**Системное изменение.** VerifiedObjectStore и VerifiedCandidateProof как общие типы. Блокировать candidate publication до audited stopped checkout; retain immutable receipts. Программные Git-проверки не должны выполнять Git effects и обходить approval.

**Regression tests.** Tamper existing object bytes under same hash: read/review/authorization fail closed; Wrong or missing receipt checkout/base/authority/parent/audit rejects; Ordinary DONE candidate passes same foreign/ignored/type/rename audit obligations as continuation; Missing stored original receipt cannot be reconstructed by guessing from SHA

**Qualification cases.** Q06; Q09; Q10; Q25; Q26; Q33; Q36; Q41

**Backward compatibility.** Legacy external:operation receipt ссылки не считать hash-bound proof. Для existing candidate — explicit re-audit/adoption when possible, otherwise block.

**Existing-run recovery.** Проверенные packet hashes подтверждают целостность предоставленного evidence, но не весь отсутствующий original object store/checkout. R58 требует live exact Git/barrier verification перед reuse; raw evidence не менять.

**Граница реализации.** Validators внутри Autopilot; trustworthiness of native observations/hook effects remains runtime boundary.

**Acceptance criteria.** Every immutable reference is verified against bytes; Normal candidate publication cannot be weaker than continuation on ownership/integrity

### REL-12 · P1 — Lifecycle qualification пока не доказывает соседние переходы; source packet неполон для release replay

**Причина.** Graph tests проверяют описательную модель, не исполнения CLI edges. Многие regression fixtures напрямую seed state и заканчиваются на dispatch или recovery, не на fresh review/integration. Выполняемые qualification scripts/часть runtime modules не включены в архив.

**Affected files / evidence.** S:tests/test_state_machine_model.py; S:tests/test_continuation_candidates.py:156–246; S:tests/test_lifecycle_repairs.py; S:RELEASE-v1.0.11.md:15–26; audit-evidence/baseline-unittest-complete.txt; audit-evidence/probe-results.json

**Минимальное безопасное изменение.** Отдельный reproducible lifecycle qualification package: real Git, deterministic fake runtime, public CLI only after bootstrap, full success and negative chains, fault injection after every durable boundary. Включить все зависимости и env manifest; source packet completeness test отдельно от software defects.

**Системное изменение.** Transition-conformance tests compare declarative table with actual guard outcomes; property-based event sequences + mutation tests removing guards. CI gate includes replay R58 sanitized fixture and 42 scenarios below; full suite and code parity mandatory before release.

**Regression tests.** Run all Q01–Q42 with exact state assertions, negative no-publication and idempotence checks; Qualification finishes multi-repair continuation→DONE→qualified reviews→integration, not at READY/dispatch; Model mutation removes uncertain edge guard: executable test must fail; Archive export validates required imports/scripts/fixtures are present

**Qualification cases.** Q01; Q02; Q03; Q04; Q05; Q06; Q07; Q08; Q09; Q10; Q11; Q12; Q13; Q14; Q15; Q16; Q17; Q18; Q19; Q20; Q21; Q22; Q23; Q24; Q25; Q26; Q27; Q28; Q29; Q30; Q31; Q32; Q33; Q34; Q35; Q36; Q37; Q38; Q39; Q40; Q41; Q42

**Backward compatibility.** Тестовые изменения не требуют run migration. Новый schema/reducer требует existing-run replay fixtures и old-reader write fencing.

**Existing-run recovery.** R58 packet can be regression fixture but needs materialized matching objects/runtime paths in test copy; do not change original paths/history in user run. Missing application checkout means no independent re-run of product regression findings.

**Граница реализации.** Большая часть внутри repo; native adapter conformance needs external runtime exercise beyond fake runner.

**Acceptance criteria.** Release is qualified by executable whole workflows, not number of unit tests alone; Missing package dependencies are reported separately from functional regressions

### REL-13 · P2 — Монолит ledger.py затрудняет согласованное изменение invariants

**Причина.** Domain validation, CLI, projections, durable storage, Git proof inspection и migrations находятся в одном модуле с прямыми state mutations.

**Affected files / evidence.** S:tools/ledger.py (5123 lines); S:design/lifecycle-model.json

**Минимальное безопасное изменение.** Сначала выделять pure validators/reducers без смены CLI и storage layout; не начинать с полного rewrite.

**Системное изменение.** После P0/P1 вынести verified storage, domain records, transition layer, proof validators и projections; declarative table генерирует guard/coverage inventory.

**Regression tests.** Parity old/new valid flows; Mutation tests on shared invariants; Performance baseline ledger read/serialization

**Qualification cases.** Q01; Q03; Q25; Q28

**Backward compatibility.** Сначала additive adapters, versioned schema only when explicit state model changes.

**Existing-run recovery.** Отдельного recovery сверх P0/P1 не требуется.

**Граница реализации.** Внутри repo.

**Acceptance criteria.** Refactor preserves observable CLI and historical object identity

### REL-14 · P2 — Runtime telemetry не различает registration, actual spawn и liveness

**Причина.** Helper регистрирует PREPARED и сразу увеличивает spawn_calls, но не владеет spawn/wait turn и не хранит полноценный runtime receipt/handle state.

**Affected files / evidence.** S:tools/ledger.py:1953–2043,2655–2705; S:references/ledger.md:99; S:SKILL.md:68–80; E:incident-report.md (dispatch/await scope)

**Минимальное безопасное изменение.** Добавить optional native-start/stop/return-observed receipts, instance ID, heartbeat observations и раздельные registration/spawn counters. Unknown остаётся unknown; не фабриковать DISPATCHED.

**Системное изменение.** Небольшой runtime adapter с подтверждением регистрации/spawn и resume protocol; conformance against actual supported runtime, no daemon promised by skill.

**Regression tests.** Registration without spawn creates safe retry/termination path; Host interrupt after spawn resumes exact attempt without spawning duplicate; Counter actual spawn changes only on observed start receipt

**Qualification cases.** Q16; Q17; Q18; Q25; Q32

**Backward compatibility.** Legacy attempts без runtime receipt имеют unknown liveness. Не заполнять fictitious timestamps/handles.

**Existing-run recovery.** R58 не требует восстановить старые UI handles; exact inbox/receipt/stop verification достаточны при безопасной reuse qualification.

**Граница реализации.** Совместно Autopilot + внешний Codex runtime; helper сам не может обеспечить wakeup/stop гарантию.

**Acceptance criteria.** No claim of guaranteed autonomous waiting without runtime evidence

## 7. Lifecycle qualification matrix

Это **спроектированный target suite**, не отчёт о выполненных 42 E2E тестах. Выполненные проверки описаны в разделе 1. Все строки должны проверяться через публичные transitions после минимального bootstrap, с real Git checkout и детерминированным runtime adapter. Значения current_candidate ниже относятся к предлагаемой явной projection; в v1.0.11 отдельного поля нет.

В каждом negative case проверять неизменность ledger bytes/revision и отсутствие частично опубликованных canonical records; orphan content-addressed bytes до publication допустимы лишь как неавторитетные объекты. В каждом positive case — owner/epoch, unique ID, exact hashes, lease safety, active findings и возможность следующей команды. Для crash case проверять как pre-commit, так и post-commit replay; не ограничиваться восстановлением JSON.

### Q01. Happy path ticket

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | EXECUTE |
| `run_control` | ACTIVE |
| `ticket_status` | INTEGRATED |
| `current_attempt` | W1 RETURNED |
| `current_candidate` | C1 integrated |
| `lease` | All released |
| `active_findings` | none |
| `historical_findings` | none |
| `authorization` | none |
| `review_state` | All required reviews qualified PASS |
| `next_action` | next ready ticket / G4 |
| `next_allowed_command` | ready-ticket or gate G4 |

**Обязательные assertions:** One commit, one review record, one integration; all cross-field invariants.

**Что есть сейчас:** Existing unit flows; full supplied E2E runner absent.

### Q02. One repair

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | EXECUTE |
| `run_control` | ACTIVE |
| `ticket_status` | INTEGRATED |
| `current_attempt` | W2 RETURNED |
| `current_candidate` | C2 integrated; parent C1 |
| `lease` | All released |
| `active_findings` | none |
| `historical_findings` | F1 resolved_by R2 with proof |
| `authorization` | A1 consumed by W2 |
| `review_state` | R1 BLOCK historical; R2 current qualified PASS |
| `next_action` | next ready ticket |
| `next_allowed_command` | ready-ticket |

**Обязательные assertions:** Original F1/return unchanged; regression proof closes F1 only.

**Что есть сейчас:** Repair helpers covered, full chain needs qualification.

### Q03. Several repairs including preserve hops

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | EXECUTE |
| `run_control` | ACTIVE |
| `ticket_status` | INTEGRATED |
| `current_attempt` | Wn RETURNED |
| `current_candidate` | Cn integrated; continuous parent chain |
| `lease` | All released |
| `active_findings` | none |
| `historical_findings` | F1..Fn resolved/superseded with dispositions |
| `authorization` | A1..An consumed; provenance readable |
| `review_state` | Current required PASS; old reviews historical |
| `next_action` | next ready ticket |
| `next_allowed_command` | ready-ticket |

**Обязательные assertions:** Per-path origins survive untouched-file hops; no scalar current_attempt loss.

**Что есть сейчас:** Transitive tests present; full chain partial.

### Q04. One repair fixes bounded set of three findings

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | EXECUTE |
| `run_control` | ACTIVE |
| `ticket_status` | INTEGRATED |
| `current_attempt` | W2 RETURNED |
| `current_candidate` | C2 parent C1 |
| `lease` | All released |
| `active_findings` | none |
| `historical_findings` | F1,F2,F3 separately verified/resolved |
| `authorization` | A{F1,F2,F3} consumed once |
| `review_state` | R2 covers three regression proofs and full ticket |
| `next_action` | next ready ticket |
| `next_allowed_command` | ready-ticket |

**Обязательные assertions:** Cross-ticket/candidate sets reject; no unverified sibling auto-close.

**Что есть сейчас:** Absent in scalar schema.

### Q05. No-change BLOCK repair

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | EXECUTE |
| `run_control` | BLOCKED |
| `ticket_status` | BLOCKED awaiting revised plan |
| `current_attempt` | Wfailed closed; history retained |
| `current_candidate` | Prior validated C remains current |
| `lease` | Stopped Wfailed released |
| `active_findings` | Blocking cause retained |
| `historical_findings` | Earlier findings preserved |
| `authorization` | Prior A consumed; next authorization not yet made |
| `review_state` | Prior review unchanged |
| `next_action` | classify cause / authorize changed repair |
| `next_allowed_command` | close-blocked-attempt then authorize-repair |

**Обязательные assertions:** No actual change, exact HEAD/tree, no pending effect.

**Что есть сейчас:** Exact DONE-parent case covered.

### Q06. BLOCK with valid nonempty write-set

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | EXECUTE |
| `run_control` | BLOCKED |
| `ticket_status` | BLOCKED |
| `current_attempt` | W1 RETURNED BLOCKED |
| `current_candidate` | C1 continuation-only |
| `lease` | Writer stopped; reservation active |
| `active_findings` | External blocker; no in-scope failure |
| `historical_findings` | Prior findings unchanged |
| `authorization` | Preserve authorization applied |
| `review_state` | Not yet reviewed |
| `next_action` | review continuation / fix blocker |
| `next_allowed_command` | prepare-review or authorize-repair |

**Обязательные assertions:** Full audit, positive focused proof; cannot integrate directly.

**Что есть сейчас:** 6 preservation tests; subsequent finalization incomplete.

### Q07. HANDOFF with partial files; also zero-file variant

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | EXECUTE |
| `run_control` | BLOCKED |
| `ticket_status` | BLOCKED |
| `current_attempt` | W1 RETURNED HANDOFF; closed for no-change |
| `current_candidate` | C1 continuation only if qualified; else prior C |
| `lease` | Reserve only verified candidate; unknown liveness quarantined |
| `active_findings` | Handoff remaining work and real blockers |
| `historical_findings` | Previous findings retained |
| `authorization` | Explicit preserve/continue plan or none |
| `review_state` | No automatic PASS |
| `next_action` | qualified continuation / safe closure |
| `next_allowed_command` | preserve-blocked-candidate or proposed close-nochange |

**Обязательные assertions:** Same criterion/check safety as BLOCK; empty HANDOFF must not strand ticket.

**Что есть сейчас:** Nonempty HANDOFF tested; empty generalized closure absent.

### Q08. External blocker with otherwise passing ticket

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | EXECUTE |
| `run_control` | BLOCKED |
| `ticket_status` | BLOCKED or READY bounded repair |
| `current_attempt` | W previous terminal |
| `current_candidate` | Continuation C unchanged |
| `lease` | Prior reserve closed only for authorized replacement |
| `active_findings` | External issue active separately from implementation findings |
| `historical_findings` | All prior evidence retained |
| `authorization` | Candidate-bound permission only |
| `review_state` | PASS does not discharge external issue |
| `next_action` | resolve external evidence / bounded repair |
| `next_allowed_command` | authorize-repair or external-resolution transition |

**Обязательные assertions:** No blanket BLOCKED→ACTIVE; full relevant suite must be satisfied or validly amended.

**Что есть сейчас:** W05 evidence and partial tests.

### Q09. Quarantine + exact reconciliation

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | EXECUTE |
| `run_control` | ACTIVE or BLOCKED if other cause |
| `ticket_status` | RUNNING or explicit blocked |
| `current_attempt` | Same returned W restored; not re-ingested |
| `current_candidate` | No new candidate until proof finalization |
| `lease` | Quarantine→active reservation under exact proof |
| `active_findings` | Specific violation resolved; unrelated blockers remain |
| `historical_findings` | Original violation/return retained |
| `authorization` | Reconciliation decision applied |
| `review_state` | No implied review PASS |
| `next_action` | prepare/finalize candidate |
| `next_allowed_command` | prepare-effect/candidate |

**Обязательные assertions:** Mismatch leaves state byte-identical; replay after later release no-op.

**Что есть сейчас:** Legacy case tested; universal replay gap.

### Q10. Stale/forked/path-specific provenance rejection

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | EXECUTE |
| `run_control` | Unchanged |
| `ticket_status` | Unchanged; not newly READY |
| `current_attempt` | Unchanged |
| `current_candidate` | Current C unchanged |
| `lease` | Unchanged; no new lease |
| `active_findings` | Same current findings |
| `historical_findings` | Same history |
| `authorization` | Invalid plan not authorized |
| `review_state` | Same reviews |
| `next_action` | diagnose lineage |
| `next_allowed_command` | validate plan / explicit recovery |

**Обязательные assertions:** Reject wrong ticket/path/base/cycle/missing origin/ambiguous same-SHA parent before authorization.

**Что есть сейчас:** Existing transitive negatives + AP-P09 gap.

### Q11. Finding without ticket binding at new ingest

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | EXECUTE |
| `run_control` | Unchanged until explicit rejection handling |
| `ticket_status` | REVIEW or BLOCKED continuation |
| `current_attempt` | Worker unchanged; reviewer awaiting valid return |
| `current_candidate` | Same C |
| `lease` | Reviewer retained until stopped/rejected closure |
| `active_findings` | No new unaddressable canonical finding |
| `historical_findings` | Old history unchanged |
| `authorization` | none |
| `review_state` | Malformed return not ingested OR canonical binding attached atomically |
| `next_action` | correct return binding / terminate reviewer |
| `next_allowed_command` | validate-return then ingest-return or terminate-attempt |

**Обязательные assertions:** No partial finding publication; original raw reported refs preserved.

**Что есть сейчас:** AP-P11 currently reproduces defect.

### Q12. Recovery of already ingested missing binding

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | EXECUTE |
| `run_control` | BLOCKED |
| `ticket_status` | BLOCKED |
| `current_attempt` | W05 RETURNED |
| `current_candidate` | ef8da4… continuation |
| `lease` | W05 reservation retained; R05 released |
| `active_findings` | Three current bound findings + external obligation |
| `historical_findings` | Seven old ticket observations classified; no deletion |
| `authorization` | Recovery decision only; no repair yet |
| `review_state` | R05 remains BLOCK, same return hash |
| `next_action` | authorize bounded repair after preflight |
| `next_allowed_command` | proposed binding-recovery then authorize-repair |

**Обязательные assertions:** Same packet/run/epoch/subject proves each binding; ambiguous inference rejected.

**Что есть сейчас:** Absent current transition; exact R58 regression needed.

### Q13. Historical versus active findings and mirrored issues

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | EXECUTE |
| `run_control` | BLOCKED until qualified resolution |
| `ticket_status` | REVIEW/BLOCKED |
| `current_attempt` | Current W |
| `current_candidate` | Current C |
| `lease` | Per live/reservation state |
| `active_findings` | Current findings plus undischarged carry-forward obligations |
| `historical_findings` | Superseded-subject findings distinct from resolved defects |
| `authorization` | Only current bounded plan |
| `review_state` | All current required review results aggregated |
| `next_action` | repair/adjudicate current obligations |
| `next_allowed_command` | authorize-repair/adjudicate |

**Обязательные assertions:** No last-review-wins; no impact-only broad issue clearing.

**Что есть сейчас:** Current code only invalidated_by projection.

### Q14. Duplicate worker return

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | EXECUTE |
| `run_control` | Unchanged |
| `ticket_status` | Unchanged |
| `current_attempt` | Same W RETURNED |
| `current_candidate` | Same C or none |
| `lease` | Unchanged |
| `active_findings` | No duplicated issue |
| `historical_findings` | No duplicated objects/records |
| `authorization` | Consumed once |
| `review_state` | Unchanged |
| `next_action` | Unchanged derived action |
| `next_allowed_command` | ingest-return replay |

**Обязательные assertions:** Exact same bytes no revision; different bytes reject through all paths.

**Что есть сейчас:** AP-P12 positive control.

### Q15. Duplicate review return and prepare retry

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | EXECUTE |
| `run_control` | Unchanged |
| `ticket_status` | Unchanged |
| `current_attempt` | Same worker; same R RETURNED |
| `current_candidate` | Same C |
| `lease` | Review released once |
| `active_findings` | No duplicate finding/mirror/verdict |
| `historical_findings` | No duplicate review history |
| `authorization` | Unchanged |
| `review_state` | Same immutable review ref |
| `next_action` | Unchanged derived action |
| `next_allowed_command` | ingest-return/prepare-review replay |

**Обязательные assertions:** Same request fingerprint no-op; integrate cannot overwrite return.

**Что есть сейчас:** AP-P13 positive; AP-P03/AP-P15 defects.

### Q16. Lost worker / timeout

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | EXECUTE |
| `run_control` | BLOCKED |
| `ticket_status` | BLOCKED |
| `current_attempt` | W LOST only after observation |
| `current_candidate` | Prior C retained |
| `lease` | Unknown stop→quarantined; proven stop→released |
| `active_findings` | Liveness/recovery issue |
| `historical_findings` | Historical attempts retained |
| `authorization` | Consumed or revoked based on actual start evidence |
| `review_state` | Unchanged |
| `next_action` | stop/qualify reuse then fresh attempt |
| `next_allowed_command` | terminate-attempt then typed recovery |

**Обязательные assertions:** Timeout is not stop; no duplicate spawn on silent handle.

**Что есть сейчас:** Termination unit tests only partial.

### Q17. Interrupted worker after/before writes

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | EXECUTE |
| `run_control` | BLOCKED |
| `ticket_status` | BLOCKED |
| `current_attempt` | W INTERRUPTED |
| `current_candidate` | Prior C; partial C only after adoption proof |
| `lease` | Released with stop+audit, otherwise quarantine |
| `active_findings` | Cause plus ownership obligations |
| `historical_findings` | Partial evidence retained |
| `authorization` | Original A consumed if dispatched |
| `review_state` | Unchanged |
| `next_action` | audit/close/adopt/revert |
| `next_allowed_command` | terminate-attempt then typed recovery |

**Обязательные assertions:** No fake DONE; preserve partial effects and foreign changes.

**Что есть сейчас:** No general outcome matrix.

### Q18. Interrupted reviewer / malformed return

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | EXECUTE |
| `run_control` | BLOCKED |
| `ticket_status` | REVIEW or BLOCKED continuation |
| `current_attempt` | Worker unchanged; R INTERRUPTED |
| `current_candidate` | Same C |
| `lease` | R released only with stop proof |
| `active_findings` | Termination/integrity blocker until retry qualified |
| `historical_findings` | Rejected review remains history, not accepted findings |
| `authorization` | none |
| `review_state` | No accepted verdict; fresh R required after changed/contaminated export |
| `next_action` | fresh qualified review |
| `next_allowed_command` | terminate-attempt then prepare-review |

**Обязательные assertions:** No re-ingest terminated return; resolve prior termination issue explicitly.

**Что есть сейчас:** Review04 evidence; current issue lifecycle incomplete.

### Q19. Continuation candidate→repair BLOCK/no changes

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | EXECUTE |
| `run_control` | BLOCKED |
| `ticket_status` | BLOCKED |
| `current_attempt` | Wrepair closed; old attempt retained |
| `current_candidate` | Prior continuation C remains current |
| `lease` | Wrepair released; reservation policy explicit |
| `active_findings` | External issue and uncorrected findings |
| `historical_findings` | All previous attempts preserved |
| `authorization` | A consumed; replacement requires causal change |
| `review_state` | Prior review remains BLOCK |
| `next_action` | changed repair / blocker resolution |
| `next_allowed_command` | proposed generalized close-blocked then authorize-repair |

**Обязательные assertions:** Validated continuation receipt allowed instead of prior DONE-only predicate.

**Что есть сейчас:** AP-P16 + static continuation closure gap.

### Q20. Continuation candidate→repair DONE candidate

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | EXECUTE |
| `run_control` | ACTIVE only after external resolution; else BLOCKED |
| `ticket_status` | CANDIDATE when full DONE qualified |
| `current_attempt` | Wrepair RETURNED DONE |
| `current_candidate` | New Cdone parent Ccontinuation |
| `lease` | Stopped writer, candidate reservation active |
| `active_findings` | No unresolved completion blocker; current findings pending re-review |
| `historical_findings` | Prior continuation and blocker closure proofs retained |
| `authorization` | A consumed |
| `review_state` | Fresh review required on new SHA |
| `next_action` | prepare required reviews |
| `next_allowed_command` | candidate then prepare-review |

**Обязательные assertions:** External fixture issue needs real evidence; no promotion of old BLOCKED verdict.

**Что есть сейчас:** Current tests stop at dispatch.

### Q21. Review after continuation

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | EXECUTE |
| `run_control` | BLOCKED |
| `ticket_status` | BLOCKED |
| `current_attempt` | Original W RETURNED BLOCKED |
| `current_candidate` | Same continuation C |
| `lease` | Review released; worker reserve retained |
| `active_findings` | BLOCK→current findings; PASS→external issue still active |
| `historical_findings` | Past returns retained |
| `authorization` | none until repair authorized |
| `review_state` | Current R BLOCK or PASS, never integration permission by itself |
| `next_action` | authorize repair / resolve blocker |
| `next_allowed_command` | authorize-repair |

**Обязательные assertions:** Both PASS/BLOCK branches have non-wait next action; no direct integrate.

**Что есть сейчас:** Preserve test partial; R58 BLOCK wait defect.

### Q22. Critical migration/data-integrity barrier

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | EXECUTE |
| `run_control` | BLOCKED until required independent axis |
| `ticket_status` | REVIEW |
| `current_attempt` | W RETURNED |
| `current_candidate` | Frozen current C |
| `lease` | Review/reservation closure per receipt |
| `active_findings` | Missing-critical-qualification until satisfied |
| `historical_findings` | Routine PASS preserved |
| `authorization` | Manual review handoff authorization if required |
| `review_state` | Routine PASS insufficient; separate critical PASS must match C |
| `next_action` | obtain critical qualified review |
| `next_allowed_command` | prepare-handoff/import-manual then integrate |

**Обязательные assertions:** Different candidate, stale receipt or role reuse cannot fulfill critical mandate.

**Что есть сейчас:** Manual helper stricter but integrate bypass AP-P04.

### Q23. Successor run after predecessor cancellation

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | DESIGN initially |
| `run_control` | ACTIVE/BLOCKED according to gates |
| `ticket_status` | Fresh planned tickets only |
| `current_attempt` | No inherited live attempt |
| `current_candidate` | Explicit baseline SHA, not inherited current pointer |
| `lease` | Predecessor all released; successor none initially |
| `active_findings` | Explicit new/current obligations |
| `historical_findings` | Read-only predecessor evidence with disposition |
| `authorization` | No inherited repair authorization |
| `review_state` | Fresh required design/current review |
| `next_action` | new G1/G2/G3 |
| `next_allowed_command` | init/publish-intent/adopt-requirements/publish-design-bundle |

**Обязательные assertions:** Predecessor remains terminal; inherited fact proven at exact SHA.

**Что есть сейчас:** Evidence has successor, no dedicated lineage transition.

### Q24. Wave boundary and dependent next ticket

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | EXECUTE or VERIFY |
| `run_control` | ACTIVE unless real checkpoint |
| `ticket_status` | Completed tickets INTEGRATED; next PLANNED |
| `current_attempt` | Closed previous worker |
| `current_candidate` | Integrated C frozen baseline |
| `lease` | No old writer; next lease only after readiness |
| `active_findings` | No unresolved applicable wave blocker |
| `historical_findings` | Earlier records historical |
| `authorization` | Next authorization only if repair |
| `review_state` | All previous required reviews qualified |
| `next_action` | next ready ticket or G4; checkpoint only if required |
| `next_allowed_command` | ready-ticket or gate |

**Обязательные assertions:** Wave is derived; old-version PLANNED tickets not executable; semi not per-ticket prompt.

**Что есть сейчас:** Derived queues documented, full chain not runnable from packet.

### Q25. Crash/restart between every durable step

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | Earliest verified phase |
| `run_control` | RECOVERING then justified state |
| `ticket_status` | Verified old or new state only |
| `current_attempt` | Exact existing attempt; never guessed started |
| `current_candidate` | Prior C or receipt-bound new C |
| `lease` | Unknown liveness quarantined |
| `active_findings` | Explicit incomplete effect/attempt |
| `historical_findings` | No lost immutable history |
| `authorization` | Preserve consumed status |
| `review_state` | Known returned or awaiting valid result |
| `next_action` | reconcile exact incomplete boundary |
| `next_allowed_command` | recover then event-specific finalization |

**Обязательные assertions:** Inject after object_store, ledger.prev, ledger.json, snapshot, spawn, Git, receipt; no half aggregate.

**Что есть сейчас:** Atomic-write tests present; effect gaps AP-P01/02.

### Q26. Idempotent retry after crash

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | Unchanged from committed result |
| `run_control` | Unchanged |
| `ticket_status` | Unchanged |
| `current_attempt` | Same IDs |
| `current_candidate` | Same candidate |
| `lease` | No duplicate lease |
| `active_findings` | No duplicate issue/finding |
| `historical_findings` | Same history |
| `authorization` | Same consumption |
| `review_state` | Same review ref |
| `next_action` | Same valid next action |
| `next_allowed_command` | same command with same semantic fingerprint |

**Обязательные assertions:** Owner fenced first; original revision retry adopted if exact effect already committed; conflict rejected.

**Что есть сейчас:** Partial idempotence, AP-P14/15 fail current expectations.

### Q27. Authorization created but not used; replace/revoke

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | EXECUTE |
| `run_control` | ACTIVE or retained external BLOCKED |
| `ticket_status` | READY with valid plan; otherwise safe BLOCKED |
| `current_attempt` | Prior closed W |
| `current_candidate` | Same C |
| `lease` | No new worker lease |
| `active_findings` | Same finding set |
| `historical_findings` | Aold superseded/revoked retained |
| `authorization` | One unconsumed current Anew |
| `review_state` | Source review unchanged |
| `next_action` | dispatch authorized plan |
| `next_allowed_command` | replace-authorization then dispatch |

**Обязательные assertions:** Any unusable unused A replaceable; consumed immutable; causal signature checked before READY.

**Что есть сейчас:** Narrow source-rebind tests; AP-P10 gap.

### Q28. Integration after several repairs

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | EXECUTE |
| `run_control` | ACTIVE |
| `ticket_status` | INTEGRATED |
| `current_attempt` | Wn RETURNED |
| `current_candidate` | Cn integrated with complete lineage |
| `lease` | All required leases released |
| `active_findings` | None applicable; no unrelated silent clearing |
| `historical_findings` | All observations retained and justified dispositions |
| `authorization` | Each A consumed exactly once |
| `review_state` | All required current PASS and integrity receipts |
| `next_action` | next ticket / G4 |
| `next_allowed_command` | integrate idempotently |

**Обязательные assertions:** No raw reread substitute; exact findings proof set; full ticket coverage.

**Что есть сейчас:** Needs new full E2E.

### Q29. Semi-mode human checkpoint versus internal wait

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | Actual phase |
| `run_control` | BLOCKED/PAUSED only for real decision; ACTIVE otherwise |
| `ticket_status` | Dependent ticket not dispatchable while pending |
| `current_attempt` | No new dependent attempt |
| `current_candidate` | Same candidate |
| `lease` | No unauthorized new lease |
| `active_findings` | Decision-required issue, not routine wait |
| `historical_findings` | Decision history retained |
| `authorization` | Explicit owner/human approval when required |
| `review_state` | Unchanged |
| `next_action` | request exact decision OR await live worker |
| `next_allowed_command` | checkpoint-answer transition / normal internal wait |

**Обязательные assertions:** No automatic prompt at every ticket/wave; no proceeding past unresolved material scope decision.

**Что есть сейчас:** SKILL documented; durable generic checkpoint not enforced.

### Q30. Several reviews same candidate / disagreement / stale review

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | EXECUTE |
| `run_control` | BLOCKED until adjudicated |
| `ticket_status` | REVIEW |
| `current_attempt` | W current; R statuses explicit |
| `current_candidate` | Exact current C |
| `lease` | Stopped R released; pending R reserved |
| `active_findings` | Union applicable blocking findings, not latest-only |
| `historical_findings` | Old-candidate review historical/nonqualifying |
| `authorization` | Adjudication exact subjects/proofs |
| `review_state` | Conflicting verdicts cannot qualify integration |
| `next_action` | adjudicate / await other live review |
| `next_allowed_command` | adjudicate or prepare-review |

**Обязательные assertions:** Different mandate string must not hide required conflicting axis; stale C return cannot qualify new C.

**Что есть сейчас:** Some exact-mandate disagreement guard exists.

### Q31. Partially valid reviewer return

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | EXECUTE |
| `run_control` | Unchanged until rejected-attempt closure |
| `ticket_status` | Same REVIEW/BLOCKED |
| `current_attempt` | No terminal result published |
| `current_candidate` | Same C |
| `lease` | No implicit release without stop proof |
| `active_findings` | No partial subset of new findings published |
| `historical_findings` | Raw rejected evidence retained separately |
| `authorization` | none |
| `review_state` | Entire return rejected if any required check/criterion/ref invalid |
| `next_action` | correct exact return before first ingest or new review |
| `next_allowed_command` | validate-return / terminate-attempt |

**Обязательные assertions:** No accepted green subset; no fabricated missing evidence.

**Что есть сейчас:** Schema strict but semantic PASS gap AP-P04.

### Q32. Dispatch registered, worker never started / handle lost

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | EXECUTE |
| `run_control` | BLOCKED only when recovery needed |
| `ticket_status` | RUNNING→safe BLOCKED/READY by typed recovery |
| `current_attempt` | PREPARED; then INTERRUPTED when nonstart proven |
| `current_candidate` | Prior C unchanged |
| `lease` | Release only confirmed no writer; else quarantine |
| `active_findings` | Runtime delivery/recovery cause |
| `historical_findings` | Registration retained |
| `authorization` | Authorization consumption corrected only by explicit no-start event, not deletion |
| `review_state` | Unchanged |
| `next_action` | inspect exact inbox/start receipt; no blind spawn duplicate |
| `next_allowed_command` | terminate-attempt / reconcile-start |

**Обязательные assertions:** Registration is not evidence of native spawn; execute once at most.

**Что есть сейчас:** Current PREPARED only; no runtime start event.

### Q33. Worker finished; commit/receipt/adoption interrupted

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | EXECUTE |
| `run_control` | ACTIVE or RECOVERING |
| `ticket_status` | RUNNING/CANDIDATE only after proof |
| `current_attempt` | W RETURNED; same attempt |
| `current_candidate` | C remains null/prior until candidate event; then new C |
| `lease` | Reservation retained |
| `active_findings` | Incomplete effect explicit |
| `historical_findings` | All receipts retained |
| `authorization` | Original authority unchanged |
| `review_state` | Review not before candidate frozen |
| `next_action` | adopt observed effect, no re-commit |
| `next_allowed_command` | ingest-return/reconcile-effect/finalize-candidate |

**Обязательные assertions:** Commit missing receipt and applied receipt without candidate both complete safely.

**Что есть сейчас:** AP-P02 reproduces applied-without-candidate gap.

### Q34. No-change initial BLOCK/FAILED and safe revert

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | EXECUTE |
| `run_control` | BLOCKED then READY only after cause resolution |
| `ticket_status` | BLOCKED→READY under explicit retry |
| `current_attempt` | Closed initial W; not invented prior candidate |
| `current_candidate` | Baseline B; no candidate invented |
| `lease` | Released only with no-write or exact owned revert proof |
| `active_findings` | Original cause active until resolution |
| `historical_findings` | Failed attempt/write fingerprints retained |
| `authorization` | New retry/repair authority explicit |
| `review_state` | No automatic review PASS |
| `next_action` | resolve cause / retry from baseline |
| `next_allowed_command` | proposed close-nochange or scoped revert-proof transition |

**Обязательные assertions:** No reset/clean/stash blanket cleanup; foreign writes preserved.

**Что есть сейчас:** Outside current close-blocked scope.

### Q35. Repair provenance source review, worker and preserve hops

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | EXECUTE |
| `run_control` | ACTIVE or retained BLOCKED |
| `ticket_status` | READY/RUNNING only when feasible |
| `current_attempt` | Fresh W |
| `current_candidate` | Current parent C uniquely resolved |
| `lease` | Exact packet zone with denies |
| `active_findings` | Findings same ticket/C |
| `historical_findings` | Full path-specific parent chain |
| `authorization` | Exact A consumed |
| `review_state` | Source review immutable |
| `next_action` | worker result→candidate or preserve as applicable |
| `next_allowed_command` | dispatch then candidate/preserve |

**Обязательные assertions:** All legitimate source forms share canonical worker parent; no create-origin in repair silently accepted without policy.

**Что есть сейчас:** AP-P08 mismatch; transitive tests cover normal chains.

### Q36. Review writes cache into pristine export

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | EXECUTE |
| `run_control` | BLOCKED |
| `ticket_status` | REVIEW/BLOCKED |
| `current_attempt` | Worker unchanged; reviewer safely terminated |
| `current_candidate` | Original C authoritative unchanged |
| `lease` | R released only after stop receipt |
| `active_findings` | Integrity issue until qualified retry |
| `historical_findings` | Rejected output retained, not qualifying |
| `authorization` | none |
| `review_state` | Return not ingested/qualified; fresh export needed |
| `next_action` | new review on clean export |
| `next_allowed_command` | terminate-attempt then prepare-review |

**Обязательные assertions:** Executable/dependency path not evidence export; mutable test copy allowed, pristine baseline checked.

**Что есть сейчас:** Review04 actual successful guard; not guarantee runtime always isolated.

### Q37. Predecessor evidence inheritance

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | DESIGN/PLAN |
| `run_control` | BLOCKED until import proof, ACTIVE once valid |
| `ticket_status` | New ticket IDs and explicit mapping |
| `current_attempt` | No carried attempts |
| `current_candidate` | Baseline commit and compatible context |
| `lease` | No inherited lease |
| `active_findings` | Unknown predecessor fact explicit blocker |
| `historical_findings` | Predecessor accepted fact/hash retained |
| `authorization` | Fresh authority only |
| `review_state` | Fresh design reviews of successor scope |
| `next_action` | G2/G3 once mappings proven |
| `next_allowed_command` | publish inheritance receipt and current design |

**Обязательные assertions:** Same name/producer ref is not proof; terminal cancelled run may contain individually accepted work.

**Что есть сейчас:** R58 CT-EVALUATION producer PREDECESSOR-T01-R14; repo files not in packet.

### Q38. Continuation→repair with own failure cannot be preserved

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | EXECUTE |
| `run_control` | BLOCKED |
| `ticket_status` | BLOCKED |
| `current_attempt` | Wrepair RETURNED BLOCKED/HANDOFF |
| `current_candidate` | Prior C unchanged; failed changes not qualified candidate |
| `lease` | Quarantine or stopped reservation pending owned recovery |
| `active_findings` | In-scope failure active, not reclassified external |
| `historical_findings` | Partial return retained |
| `authorization` | A consumed; preserve request rejected |
| `review_state` | No qualifying PASS |
| `next_action` | diagnose/fix in-scope issue |
| `next_allowed_command` | typed partial recovery then fresh repair |

**Обязательные assertions:** Cannot mark every required check external to avoid focused proof; HANDOFF criteria same safety.

**Что есть сейчас:** Negative focused-check test exists; all-external/HANDOFF criteria loopholes static.

### Q39. Cancellation and terminal retry

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | Any current phase |
| `run_control` | QUIESCING→CANCELLED only with proof |
| `ticket_status` | Unfinished tickets CANCELLED |
| `current_attempt` | Inflight attempts INTERRUPTED |
| `current_candidate` | Last owned candidate/checkpoint retained |
| `lease` | All released only after verified stop/effect closure |
| `active_findings` | Termination reason retained, not goal success |
| `historical_findings` | All work history retained |
| `authorization` | Unconsumed authority revoked; consumed historical |
| `review_state` | No review-based acceptance implied |
| `next_action` | read-only inspect / explicit successor |
| `next_allowed_command` | cancel finalize then init successor |

**Обязательные assertions:** Fresh dispatch during QUIESCING rejected; recover cannot resurrect terminal; concurrent owner fenced.

**Что есть сейчас:** AP-P06/07 current violations.

### Q40. Takeover with old-epoch inflight attempt

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | Current phase |
| `run_control` | RECOVERING/BLOCKED until reuse qualified |
| `ticket_status` | BLOCKED affected ticket |
| `current_attempt` | Old W/R retained old epoch |
| `current_candidate` | Prior C retained |
| `lease` | Old authority quarantined; later explicit stop/reuse closure |
| `active_findings` | Liveness/ownership issue |
| `historical_findings` | Old return only historical until validated adoption |
| `authorization` | New epoch requires new explicit authorization |
| `review_state` | Old review nonqualifying until exact recovery proof |
| `next_action` | qualify stop, reconcile, resume |
| `next_allowed_command` | recover --takeover then proposed takeover-reconciliation |

**Обязательные assertions:** Epoch increment is fencing, not killing processes; no old-epoch release shortcut.

**Что есть сейчас:** Takeover test exists; generic closure missing.

### Q41. Actual write-set, deny, identity and object tamper

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | EXECUTE |
| `run_control` | BLOCKED on integrity violation; otherwise unchanged rejection |
| `ticket_status` | Same safe ticket state |
| `current_attempt` | Original exact attempt |
| `current_candidate` | Last verified C only |
| `lease` | Quarantine for actual unknown foreign effects |
| `active_findings` | Ownership/integrity blocker |
| `historical_findings` | Tamper evidence preserved |
| `authorization` | No new authority |
| `review_state` | No qualification on unverified object |
| `next_action` | audit/restore verified evidence through authorized path |
| `next_allowed_command` | validate/audit-write-set/recovery |

**Обязательные assertions:** Tracked/untracked/ignored/rename/type/symlink/mode + digest + ticket/kind identity; no hash-as-truth assumption.

**Что есть сейчас:** Audit tests pass; AP-P05 and stored_payload hash gap.

### Q42. Producer/consumer contract readiness before EXECUTE

| Поле | Ожидаемое состояние |
|---|---|
| `run_phase` | DESIGN/PLAN then EXECUTE |
| `run_control` | BLOCKED if unexecutable; ACTIVE if proven |
| `ticket_status` | Consumer PLANNED until producer readiness |
| `current_attempt` | None/new producer as permitted |
| `current_candidate` | Baseline/producer candidate per proof |
| `lease` | No premature consumer lease |
| `active_findings` | Explicit unavailable input blocker |
| `historical_findings` | Accepted contract history retained |
| `authorization` | No consumer dispatch authority before readiness |
| `review_state` | G2/G3 cover dependency availability |
| `next_action` | resolve contract plan / integrate producer / ready consumer |
| `next_allowed_command` | publish-design-bundle / ready-ticket |

**Обязательные assertions:** Spec-active distinct from implementation-available; proposed input must have actual transition or early rejection.

**Что есть сейчас:** Self-produced tests pass; remaining availability gap static.

### Gate запуска suite
Сначала Q01–Q04 и Q19–Q22/Q28 должны завершаться полноценной integration, а не остановкой на authorize/dispatch. Затем Q05–Q18, Q25–Q27 и Q30–Q42 проверяют negative/recovery boundaries. Q23/Q24/Q37/Q39/Q40 проверяют multi-run ownership. В CI добавить mutation tests: удаление проверки wrong-candidate, invalid check outcome, stop receipt, deny precedence, uncertain finalization или finding currentness обязано ломать соответствующий E2E тест. Native runtime conformance выполнять отдельно: fake adapter не доказывает, что реальный host сохранит turn или остановит дочерний процесс.

## 8. Recovery plan для Idea Scout revision 58

**Это проект переходов, а не выполненное восстановление.** Исходные архивы, state Idea Scout и source Autopilot не изменялись. Новые названия recovery events ниже — спецификация для реализации; на v1.0.11 таких CLI-команд нет. Нельзя выдавать их за готовую последовательность команд для копирования.

### 8.1. Точка восстановления и неизменяемые факты

| Сущность | Зафиксированное состояние |
|---|---|
| Run | `2026-09-17-idea-scout-v2-successor`, revision `58`, phase `EXECUTE`, control `BLOCKED` |
| Intent | revision `2`, hash `ffe8fb5a5347f7384a78e911abada38938a9e05b661caf9366e20088b31032e7` |
| Current design publication | `idea-scout-v2-design-bundle-successor-v3`, published_revision `14`, hash `2b862ffe568c9d86166861dd9910c0491162d601b2765b8bf956035f3729f3da` |
| Ticket | `T02-R17`, `BLOCKED`, current_attempt `T02-R17-WORKER-05` |
| Worker05 | `RETURNED`, исходный verdict `BLOCKED`, lease `active`; наличие lease само по себе не доказывает живой процесс |
| Candidate | `ef8da4ff49cc7f8014d90f463acf8319ad7c1335`, **continuation-only**, tree `eb86d12ccb6f75f5337c18d0480f5ae16c131721` |
| Candidate base | `9aa5501870352b87538355d14bb68dbde544c3ed` |
| Review05 | `T02-R17-REVIEW-CODE-05`, `RETURNED`, verdict `BLOCK`, lease `released` |
| Review packet hash | `e8b28341a5e2202e22c0281de105780bc92b9d5079f7104df9475bdf26001a00` |
| Review return hash | `e977b0f75bde0456a1a644fb82ad683f31ae10926b804b5798b8912ddc5dcd1c` |
| Stored next_action | `await_blocked_candidate_review` с refs на Review05/Worker05; устарел |
| Findings | 21 всего: 11 ранее invalidated design findings + 10 ticket-review findings без invalidation; из последних 3 относятся к current Review05, 7 — к предыдущим reviews |
| Issues | 17 blocking по нынешнему predicate `impact=blocking && !invalidated_by`; в `lifecycle.issue_refs` лишь 7, поэтому этот список нельзя считать полным active index |

[E: `state/successor/rev-058-ledger.json`; `reviews/review05-packet.json`; `reviews/review05-return.json`; `receipts/worker05-continuation-receipt.json`.]

Три current observations:

| Finding | Содержание принятого review | Соответствующий issue-mirror |
|---|---|---|
| `finding-e977b0f75bde-1` | Нет durable active extraction revision для результата с нулём semantic signals | `issue-6052c0b24e4aa5ea` |
| `finding-e977b0f75bde-2` | Не обеспечено точное соответствие questions / normalized rows / outcomes / QUICK refs | `issue-1fec003177035f88` |
| `finding-e977b0f75bde-3` | Delete + recreate допускает повторное использование Search Run identity с изменёнными settings | `issue-97733f767ad71380` |

Это содержание независимого Review05, а не мои независимо исполненные SQL-пробы Idea Scout: application checkout не приложен. Для данного lifecycle review достаточно доказать, что canonical review принят, его subject однозначен, а следующий repair не может использовать findings.

### 8.2. Сначала — release и compatibility barrier

До любых новых writers на T02 нужно квалифицировать семь P0 из раздела 6 и установить совместимую версию helper/skills/schemas. Снять новую read-only копию актуального state; убедиться, что живой run всё ещё соответствует ожидаемым revision, owner, epoch, intent и candidate. Redacted owner token в архиве не является полномочием на реальные mutations. Если реальное состояние уже изменилось, recovery проектируется относительно нового snapshot, а не применяется насильно к revision 58.

Новый release должен определить `schema_version`/compatibility floor и не позволять старому writer игнорировать новые binding/disposition/candidate поля. Политика совместимости может быть более строгой, чем простое повышение patch-версии. Нельзя запускать два helper разных версий как взаимозаменяемых owners одного run.

**Отдельный обязательный compatibility gate: current design bindings.** Pure validator v1.0.11 отвергает 13 пересечений `ticket.contract_refs` с `contract.producer_refs`. Первое — `T02-R17 → CT-V2-ARCHITECTURE-R17`; следующие затрагивают T03 и дальнейшие tickets. Все эти contracts уже `active`: это не буквальное повторение старого proposed-input incident, но реальный конфликт legacy state с нынешним invariant. [S: `tools/ledger.py:865–892,2046–2069`; `audit-evidence/revision58-binding-revalidation.json`.]

Безопасные варианты:

1. Если canonical design documents подтверждают, что это лишь неверная классификация input/output **без изменения scope, требований и смысла contract**, создать отдельный версионированный binding-normalization overlay с owner authorization, old/new classification, dependency impact и focused design review. Исходный publication и его hash сохранить. Все consumers должны использовать одну effective binding projection; новый validation receipt относится к overlay + исходному immutable bundle.
2. Если такая эквивалентность не доказана, необходим versioned replan/intent amendment либо новый successor с explicit carry-forward evidence. Это уже не metadata-only repair и требует соответствующих gates.

**Нельзя автоматически удалить все 13 `contract_refs` только потому, что так предлагает ошибка validator.** Принятый архитектурный contract может описывать одновременно то, что implementation должен соблюдать, и его производимый результат; из JSON без canonical docs семантика не устанавливается. В архиве этих исходных project-local документов недостаточно. Поэтому возможность полностью same-run восстановления является **условной**, а не обещанной. Новая команда не должна обходить эту неопределённость. Ordinary `publish-design-bundle` в EXECUTE после выполненных attempts не является готовым способом такого исправления.

### 8.3. Append-only binding recovery трёх findings

Предлагаемый event `recover-review-finding-bindings` принимает:

- exact run/revision/epoch/intent и current publication identity;
- `source_attempt=T02-R17-REVIEW-CODE-05`, exact packet/return hashes;
- `ticket=T02-R17`, worker source `T02-R17-WORKER-05`, candidate `ef8da4…`;
- explicit bounded finding IDs `finding-e977b0f75bde-1..3`;
- отдельное обоснование связи и owner-authorized decision ID.

Validator проверяет **каждую** связь через registered review subject/fingerprint и candidate lineage. Из одного лишь глобально известного `C-V2-07` нельзя угадать ticket. В данном packet subject подтверждён прямой review context. Неоднозначный, stale или конфликтующий subject — reject без publication.

Публикация добавляет canonical binding в отдельный overlay/decision и пересчитывает findings/issue-mirrors projection. Исходные `reported_affected_refs`, bytes `review05-return.json`, `return_ref` и hash не изменяются. Поле `affected_refs` в старом immutable evidence не «дописывается задним числом». Нельзя переингестить отредактированный return под тем же attempt ID: это нарушило бы exact-return identity, даже если helper сейчас позволяет обход через integrate.

Повтор того же decision — no-op, включая повтор после последующих легитимных transitions. Конфликтующие новые bindings — отдельная явно adjudicated коррекция, не молчаливая перезапись.

### 8.4. Current, historical и unresolved — три разных понятия

Предлагаемый `reconcile-ticket-review-lineage` должен построить следующий projection:

- **Current review observations:** три findings Review05 на candidate `ef8da4…`.
- **Historical ticket observations:** `finding-f989a2c3e524-1`, `finding-bcbdeeded833-1..5`, `finding-22bf0f5a4fde-1`. Они остаются в истории и больше не описывают current subject буквально.
- **Unresolved obligations:** current findings + каждый ещё не доказанно закрытый historical defect/carry-forward + применимые внешние/операционные blockers.

`superseded_subject` не означает `resolved`. Нельзя автоматически объявить семь исторических дефектов исправленными на основании того, что последний reviewer их не повторил. Для каждого нужны конкретный regression result + qualified review coverage либо explicit link в carried-forward finding. Если такого proof нет, obligation остаётся blocking. Исторический `finding-f989a2c3e524-1` тоже не имеет ticket в reported refs; при необходимости его projection связывается по контексту **его** Review01, не через копирование метаданных Review05.

Старые review verdict-issues выводятся из полного набора dispositions связанных obligations; не обнуляются массово. Для Review04 termination `attempt-T02-R17-REVIEW-CODE-04-interrupted` уже есть stopped/released evidence и fresh Review05. После проверки связи допустим typed disposition `recovered_by_fresh_attempt`, не фиктивный PASS interrupted review. `review04-return-not-ingested.json` не становится canonical автоматически.

W04 scope issue `issue-b5315db91291e13b` требует отдельного подтверждения: свежая authorization действительно включила нужную fixture path и соответствующее исправление проверено. Сам факт `close-blocked-attempt` восстанавливает continuation, но не доказывает разрешение scope/fixture причины. W05 external issue `issue-62c0073109c9529a` **остаётся blocking**, пока не выполнено его собственное resolution condition. Наличие новой review не закрывает его.

Все dispositions — append-only, с source evidence и effective projection. Уже invalidated 11 design findings не реактивировать. `lifecycle.issue_refs` пересчитывать или объявить summary-only; ни authorization, ни integration не должны использовать его как неполный substitute для полного issue index.

### 8.5. Один bounded repair для трёх findings

**Да, три current implementation findings можно передать одному worker**, но после расширения и квалификации repair contract. Ограничение «один finding — один worker» не является необходимым условием traceability.

Новый контракт должен содержать `finding_refs[]`, source review/worker/candidate, per-finding hypothesis, разрешённые paths/operations, проверяемые regression obligations и точные ограничения. Все три findings принадлежат одному T02, одному Review05, одному candidate и одному intent. Union write-set остаётся внутри исходного ticket scope и назначается **новой** lease. Новые unrelated findings/другие tickets в batch не добавляются. Scalar legacy `finding_ref` читается как singleton, но не как разрешение ремонтировать всё подряд.

Исходный T02 scope включает 8 paths: `migrations/009_v2_core.sql`, `tests/test_v2_store.py`, `tests/test_v2_migrations.py`, `src/idea_scout/types.py`, `src/idea_scout/store/store.py`, `src/idea_scout/store/db.py`, `src/idea_scout/store/migrate.py`, `tests/test_types.py`. У Worker05 lease только на первые три с операцией modify. Это не означает, что следующему repair запрещены остальные пять навсегда: они могут войти в новый bounded contract при обосновании, но **не расширяются молча через reuse старой lease**. [E: `attempts/worker05-packet.json`; `state/successor/rev-058-ledger.json#/tickets`.]

Перед batch authorization evaluator обязан подтвердить, что предлагаемый patch действительно помещается в T02. Если реализация требует новых требований, чужих ownership zones или затрагивает продуктовую неопределённость, необходим отдельный scope decision. Решение об этих application-level details невозможно получить только из orchestration archives.

### 8.6. Invariants перед dispatch

| Инвариант | Требуемое значение/проверка |
|---|---|
| Authority | Единственный owner; актуальные token/epoch/revision; runtime/schema совместимы; terminal predecessor не активирован повторно |
| Design context | Intent revision 2 и current R17 context; несовместимые 13 bindings получили проверенное решение, не silent edit |
| Ticket | `READY` только после принятой исполнимой authorization; до неё `BLOCKED` корректен |
| Current candidate | Явно `ef8da4…` continuation-only; источник Worker05 + exact receipt; не откат к Worker03 |
| Current attempt | До dispatch — Worker05; после — новый worker. Current candidate сохраняется отдельно, пока нового candidate нет |
| Parent chain | `W01 b5ce… → W02 ea51… → W03 9aa550… → W05 ef8da4…`; W04 без candidate не является parent hop |
| Repair base | Exact current candidate `ef8da4…`, не его base `9aa550…`; path-specific lineage для create→modify |
| Authorization | Одна current unconsumed authorization, exact contract object; bounded 3 findings + явные carry-forward obligations; применимые source/causal guards уже проверены тем же validator, что используется dispatch |
| Leases/liveness | Реальный writer Worker05 остановлен; активная reservation освобождается доказуемым transition, не по таймауту/предположению; нет quarantined или concurrent conflicting writers |
| Git/effects | Actual authoritative root/HEAD/tree/parent/audit проверены; нет unresolved prepared/uncertain effects; отсутствующие bytes/fixtures не выдумываются |
| Review | Review05 terminal/released; Review04 interrupted/released и typed recovery disposition; свежий worker не переиспользует reviewer attempt |
| Packet | Новый unique ID, fresh exact inbox, canonical Worker05 source, current candidate fingerprint, required checks и manual critical requirement |
| Findings | Три bindings valid; historical obligations получили доказанные dispositions/carry-forward; external fixture blocker не стёрт |
| Next action | До dispatch — исполнимый repair action с перечислением retained blockers; после actual registration — внутренний await_worker_return, не user checkpoint |

Run control может оставаться `BLOCKED` из-за документированного внешнего препятствия, пока **специально разрешённый bounded repair** выполняется. Поэтому системное исправление guards не должно означать примитивный запрет любого dispatch при BLOCKED; нужны reason-aware разрешённые events. В то же время QUIESCING/terminal не должны позволять новый worker.

### 8.7. Возвращение continuation candidate в обычный lifecycle

```text
R58 BLOCKED + continuation ef8da4…
  → qualified compatibility / binding / finding-disposition recovery
  → executable bounded repair authorization (3 current findings)
  → new worker based exactly on ef8da4…
  → actual write-set audit + required checks
  → DONE return only when DONE semantics really satisfied
  → ordinary candidate commit + bound effect receipt
  → independent routine review + separately required critical qualification
  → immutable qualified review aggregate + post-review integrity
  → integrate ordinary DONE candidate
  → next eligible ticket, not premature G4
```

**Внешний blocker нельзя пропустить.** Worker05 сообщил 11 `evaluation_v2` failures из-за отсутствующих authoritative decision/review documents и SQLite fixtures в exact packet base, вне его lease. Review05 сообщает 152 required-suite PASS и 565 PASS с 12 deselected в расширенном запуске. Эти результаты не доказывают прохождение исходной полной обязательной suite и не закрывают external issue. [E: `attempts/worker05-return.json`; `reviews/review05-return.json`; R58 issue `issue-62c0073109c9529a`.]

Для полного DONE требуется восстановить **авторитетные**, а не придуманные, evaluation resources через разрешённый environment/workstream scope и повторить exact suite; либо провести настоящий authorized versioned change oracle/environment с impact review. Нельзя просто удалить failing check, сделать его optional или повторить suite с исключениями ради зелёного статуса.

Если внешнее условие ещё не выполнено, новый worker вправе снова вернуть BLOCKED с полезными изменениями. Тогда допустим ещё один audited preserve-hop; он снова **не интегрируем напрямую**. Если изменений нет, generalized no-change closure должен вернуть прежний continuation candidate `ef8da4…`, сохранив обе попытки и новую blocker-причину. Если worker потерян, lease остаётся quarantined до проверяемого stop/reconciliation, а не освобождается по предположению.

Когда worker действительно возвращает DONE, ordinary candidate имеет новый SHA и parent `ef8da4…`; Worker05 сохраняет исходный BLOCKED и continuation receipt. Finalization требует actual audit + matching operation/receipt/candidate identity. Crash после commit должен допускать adoption уже applied effect без второго commit. Команда не должна менять тип старого continuation candidate на DONE задним числом.

Новый candidate нуждается в fresh independent review. Routine Review05 явно не заменяет отдельно требуемую manual critical migration/data-integrity axis. Нужно исполнить эту qualification на **новом** candidate согласно packet/contract, с exact context, stop и post-review integrity receipts. Успех routine review не снимает critical requirement. Финальная disposition каждого current и carried-forward defect должна ссылаться на конкретные проверки; batch authorization не означает batch auto-resolve.

Интеграция потребляет immutable accepted review refs и aggregate required reviews, а не mutable файл в inbox. После неё: T02 `INTEGRATED`, current candidate — новый обычный DONE candidate, leases закрыты, применимых unresolved findings/blockers нет, old returns/receipts остаются. Следующее действие выводится из current R17 DAG: T03 может стать eligible при выполненных dependencies. G4 возможен только после всех требуемых tickets, не после одного T02. **Все P1 из раздела 6 закрыть до запуска T03.**

### 8.8. Acceptance самого recovery

Recovery квалифицирован, если повтор всей последовательности на копии legacy R58 не меняет исходные evidence hashes, не теряет Worker05 work-set, не активирует predecessor, сохраняет independent review boundary и заканчивается допустимым следующим transition. Повтор каждого уже принятого event должен быть no-op или возвращать точный ранее опубликованный receipt, даже если run продвинулся дальше. Конфликтующий replay обязан отказать без partial publication.

Нельзя заранее назначить «после этого будет revision 59»: число durable events зависит от выбранной versioned migration и разрешения bindings/environment. Обязательны monotonic revision, проверяемая цепочка решений и owner fencing, а не заранее придуманная нумерация.

## 9. Recommended release scope

### 9.1. Решение о версии

**Основной вариант — v1.1.0.** Это контролируемый refactor существующего state helper с сохранением фаз, authority model, receipts и основной методологии. Причина не размер патча, а изменение семантики current state, finding lifecycle, repair set и recovery/qualification contracts. Эти изменения требуют совместимости для existing runs и полноценного migration/recovery gate.

`v1.0.12` разумен лишь как строго ограниченный backport уже квалифицированного P0-пакета, если его можно выполнить без несовместимой схемы и если release notes честно ограничат supported paths. **Очередного patch только для affected_refs недостаточно.** Даже такой backport обязан закрыть competing integrate path, failed-check/critical barrier, effect closure, source/provenance consistency и R58 binding compatibility. Поскольку это уже семь взаимосвязанных P0, предпочтительнее одна содержательная v1.1.0, а не косметическое переименование той же серии hotfixes.

### 9.2. Пять изменений с максимальным эффектом

| Изменение | Какие классы закрывает |
|---|---|
| Общий candidate/repair eligibility validator + явный current_candidate и bounded finding set | Missing/stale sources, authorization→dispatch mismatch, continuation hops, history/current confusion |
| Единственный immutable review acceptance path + aggregate qualification | BLOCK→PASS replacement, duplicate records, failed independent checks, missing critical reviews, stale candidate evidence |
| Typed transition guards + один derived next_action / active obligations projection | Await уже завершённого review, active/current contradictions, dispatch during quiesce, terminal resurrection |
| Полный эффект/lease recovery protocol с exact receipts и idempotent adoption | Commit уже сделан, ledger не догнал; uncertain trap; no-change/continuation closure; lost/restarted workers |
| Реально исполняемый lifecycle suite на соседних transitions + fault injection | Локально зелёные validators при глобально недостижимом workflow; regressions после очередного recovery patch |

Необязательно сразу разносить весь `ledger.py` по десяткам модулей. Начать с pure validators/projectors и thin transition wrappers, сохранить работающие command interfaces; организационный split REL-13 выполнить после стабилизации behaviors. Архитектурная цель — уменьшить количество разных реализаций одного invariant, а не увеличить абстракции.

### 9.3. Release gates и rollout

**Gate R1 — baseline.** Полный source/fixture packet, pinned hashes, запуск existing suite без пропусков обязательных dependencies. Известный opt-in production-specific test допустимо отдельно документировать. Release note counts не заменяют исполнение.

**Gate R2 — regressions.** Все отрицательные AP-P01–P11/P14–P16 меняют поведение на безопасное согласно их assertions; AP-P12/P13 остаются idempotent no-op. Для predicate probes добавить полноценные CLI lifecycle cases. Неверное evidence должно отвергаться **до** canonical state publication.

**Gate R3 — qualification.** Исполнить Q01–Q42 с real Git effects, детерминированными attempt IDs, immutable returns, fault injection до/после каждого durable boundary. Не считать pass проверки декларативного graph эквивалентом pass реальных transitions.

**Gate R4 — legacy recovery.** На полноценных локальных копиях прогнать старый quarantined run, defective/rebound authorization, no-change close, preserved BLOCKED candidate и actual R58 recovery. Supplied redacted packet годится для projection/identity tests, но не для утверждения о полной original byte/hash-chain верификации. 13 binding intersections требуют реальных canonical documents для окончательного решения.

**Gate R5 — native adapter.** Проверить real dispatch/wait/finish/interrupt/stop и возобновление после потери пользовательского turn. Stop receipt не может быть просто желаемым словом `PASS`; нужны exact subject/runtime evidence и отсутствие дальнейшего writer activity.

**Rollout:** сначала serial T02 с сохранёнными snapshots и наблюдаемыми transitions; затем P1 gate и T03; затем небольшой многотикетный run с repairs, boundary и restart. Не включать параллельных overlapping writers ради теста на живом продукте. При ошибке — quiesce и диагностика, а не принудительный повтор effect.

### 9.4. Прямая инженерная оценка

1. **Можно ли продолжать Idea Scout на v1.0.11?** Read-only diagnosis и сохранение stopped evidence — да. Обычный autonomous T02 repair→integrate без hardening/recovery — нет, не рекомендую.
2. **Нужен ли новый release?** Да. Prevention без восстановления existing state не решает revision 58; recovery без исправления следующих transitions тоже недостаточен.
3. **v1.0.12 или v1.1.0?** Предпочтительно v1.1.0 по scope выше, не полный rewrite.
4. **Что наиболее полезно?** Пять взаимосвязанных изменений в таблице 9.2, прежде всего единые projections и immutable qualified integration.
5. **Что не решается одним skill?** Фактическое выполнение/остановка native workers, wake-up/turn transport, правдивость runtime receipts, часть Git/filesystem side effects и доступность внешних evaluation resources.
6. **Достаточно ли после этого для длинного run?** После реализации и успешных R1–R5 gates — разумная база для контролируемого длинного multi-ticket run. По одному проекту патча или числу unit tests такое заключение делать нельзя.
7. **Останутся ли риски?** Да: прежде всего смысловая корректность validators/reviews, реальный adapter, migration старых runs и crash/concurrency границы. Подробности ниже.

## 10. Residual risks

### 10.1. Внешний runtime

Skill может задавать обязанность дождаться worker, запрет завершать orchestration на обычном await и recovery policy; helper может сделать intent/registration/receipt durable. Но они не гарантируют доставку следующего turn, продолжение model execution, фактический spawn или остановку дочерних процессов. Надёжность требует связки с adapter: actual start receipt, liveness/heartbeat или poll, bounded timeout, stop acknowledgement с проверяемым subject и wake-up/restart mechanism. Нельзя устранять паузу просто автоматическим user checkpoint: это меняет semi-mode semantics.

### 10.2. Evidence truth и независимость review

SHA-256 защищает identity bytes, а не истинность написанного `PASS`. Object-store rehash и typed receipts снижают случайную порчу/подмену; необходимы независимые исполненные проверки, реальные environment fingerprints и honest coverage. Два reviewer IDs не доказывают независимость контекста. Critical review qualification должна опираться на требуемый manual protocol, а не на name/role строку. Сам actual application behavior по supplied archives не был заново проверен.

### 10.3. Crash, concurrency и side effects

Атомарный ledger file не делает Git commit, object publication, receipt, external process и snapshot одной атомарной операцией. После fix effect state machine остаётся необходимость reconciliation между наблюдаемым Git и intended effect. Git hooks, работа стороннего процесса, filesystem mode/rename/symlink и stale roots могут нарушить assumptions между audit и commit; нужны exact identity checks и консервативный stop при uncertainty. Owner token не останавливает уже запущенный старый процесс физически.

### 10.4. Legacy migration и смысл контрактов

Новые schemas/guards могут сделать старое state unreadable или перестать понимать previously accepted objects. Поэтому совместимый reader, explicit writer floor, dry-run recovery classification и append-only decisions обязательны. Особенно опасно молча исправлять 13 input/output intersections: текущие active contracts не раскрывают всей семантики документа. Неоднозначность должна вести к replan, а не к выдуманному output-only binding.

### 10.5. Границы этого review

Архив позволяет уверенно показать обнаруженные predicates и их контрпримеры, но не исчерпывает все reachable states. Полный repo, installed runtime, application checkout, canonical docs и некоторые historical snapshots/fixtures отсутствуют; существующие release qualification claims подтверждены не полностью. 16 isolated probes не являются exhaustive verification, а 42-case matrix — спецификация будущего suite. Даже успешный suite не доказывает отсутствие ошибок на всех последовательностях, размерах run и сбоях среды.

**Итог:** основной риск сейчас не в том, что Autopilot «слишком сложный», а в том, что одна сущность получает разные определения на разных переходах. Сохранять уже полезную методологию и evidence дисциплину разумно; продолжать наращивать независимые exception-команды без общего transition contract — нет. Следующий release должен доказывать не только безопасность каждого шага, но и наличие безопасного следующего шага для произведённого им состояния.

---

## Приложение A. Полная карта legacy input/output intersections R58

| Ticket | Contract, одновременно input и self-produced | Состояние contract |
|---|---|---|
| T02-R17 | CT-V2-ARCHITECTURE-R17 | active |
| T03-R17 | CT-V2-ARCHITECTURE-R17 | active |
| T03-R17 | CT-V2-RUNTIME-R17 | active |
| T04-R17 | CT-V2-QUICK-R17 | active |
| T04-R17 | CT-V2-SEMANTIC-R17 | active |
| T05-R17 | CT-V2-EVIDENCE-R17 | active |
| T05-R17 | CT-V2-SECURITY-R17 | active |
| T06-R17 | CT-V2-ARCHITECTURE-R17 | active |
| T06-R17 | CT-V2-ASSESSMENT-R17 | active |
| T07-R17 | CT-V2-API-UI-R17 | active |
| T08-R17 | CT-V2-SECURITY-R17 | active |
| T10-R17 | CT-V2-MIGRATION-R17 | active |
| T11-R17 | CT-V2-ARCHITECTURE-R17 | active |

Источник: current publication ticket IDs + ledger contracts в `E:state/successor/rev-058-ledger.json`; независимая pure validator проверка — `audit-evidence/revision58-binding-revalidation.json`. Это 13 **пересечений**, не 13 разных дефектных tickets и не 13 proposed contracts.

## Приложение B. Состав дополнительных audit evidence

- `baseline-unittest-complete.txt`: полный stdout/stderr существующего suite, включая все восемь dependency-related failures/errors и один skip.
- `reproduce_lifecycle_gaps.py`: isolated counterexamples/positive controls на неизменённом source; использует временные fixtures, не Idea Scout.
- `probe-results.json`: observed/expected результаты AP-P01–AP-P16; различает CLI transition и predicate-level probes.
- `probe-run.txt`: завершение запуска этих probes.
- `packet-verification.json`: source/evidence hashes и structural snapshot validation.
- `revision58-binding-revalidation.json`: direct validation current frozen bindings, 13 intersections и явное ограничение отсутствующих canonical docs.

Структурированный companion JSON содержит те же 14 findings с priorities, evidence, root causes, corrections, qualification links и recovery requirements, а также 42-case matrix. Он не является инструкцией автоматически мутировать production run без соответствующих authority/compatibility gates.
