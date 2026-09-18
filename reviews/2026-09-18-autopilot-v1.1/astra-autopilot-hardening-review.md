# Codex Autopilot v1.0.11 — независимый adversarial hardening audit

**Дата:** 18 сентября 2026. **Объект:** source packet v1.0.11 и frozen Idea Scout V2 evidence packet. **Результат:** NEEDS SYSTEMIC HARDENING; не разрешение возобновлять T02. **Рекомендуемый выпуск:** v1.1.0, без полного rewrite.

Обозначения источников: `source/…` — путь внутри `autopilot-hardening-source.zip`; `evidence/…` — внутри `autopilot-hardening-evidence.zip`. Для Python приведены номера строк поставленного `tools/ledger.py`; для JSON — имя коллекции/ID или selector. `P01–P32` — самостоятельно выполненные диагностические пробы из приложенного reproduction bundle. `Q01–Q40` — предлагаемая qualification suite, а не уже успешно пройденные тесты.

**Разделение доказательств:** [EXECUTED] — выполнено на неизменённом supplied Python code в disposable fixtures; [FROZEN] — прочитано из архивов; [STATIC] — вывод по коду; [PROPOSED] — проектируемое исправление. Не выполнялись live recovery, продуктовые изменения, native Codex dispatch, полная перепроверка трёх дефектов Idea Scout на его Git candidate. Сам product repository в пакет не входит.

## 1. Executive verdict

**Продолжать Idea Scout T02 на v1.0.11 не следует.** Причина не ограничивается отсутствующим `T02-R17` в трёх `affected_refs`. Воспроизведены нарушения двух разных свойств: (1) допустимое состояние, из которого следующий штатный шаг невозможен; (2) допустимый переход, который ошибочно обходит уже принятый BLOCK, scope/identity guard либо обязательную проверку.

Ключевой вывод: **у Autopilot есть достаточно сильные отдельные механизмы, но нет единой исполняемой модели их композиции.** Строгие continuation/provenance/reconciliation проверки соседствуют со значительно более слабыми ordinary candidate/integrate/manual-import paths. Система способна одновременно хранить `INTEGRATED` ticket и `review_result=BLOCK`, либо после принятого review продолжать durable ожидание этого же return. Это не исправляется только дополнительными указаниями модели.

Полный rewrite не обоснован. Следует сохранить owner/revision fencing, immutable evidence objects, Git audit, current design publication binding, no-silent-quarantine-release и независимый review. Нужен ограниченный структурный refactor: единая transition/admission layer, явный current candidate, общая finding/obligation projection, согласованная effect completion и versioned migration.

| Решение | Вывод |
| --- | --- |
| Безопасно ли продолжать v1.0.11? | Нет для нового T02 worker/integration; read-only inspection и сохранение evidence допустимы. |
| Hardening release до T02? | Да. Девять структурных P0 групп ниже затрагивают текущий и ближайший lifecycle. |
| v1.0.12 или v1.1.0? | v1.1.0: semantic state model, migration, grouped authorization и unified guards меняют контракт больше, чем patch. Номер сам по себе не критерий качества. |
| Нужен ли новый product run? | Не автоматически. Targeted auditable migration rev58 предпочтительнее нового successor для обхода ledger bugs. Material scope change решается отдельно. |
| Можно ли обещать отсутствие orchestration bugs? | Нет. Можно квалифицировать конечный набор переходов/guard combinations и fault windows; внешние runtime failures и неизвестные сценарии остаются. |

### 1.1. Что фактически проверено

| Проверка | Результат | Граница вывода |
| --- | --- | --- |
| Integrity source manifest | 59 entries: все SHA-256 совпали | Внутренняя целостность packet; не независимая аттестация upstream commit. |
| Integrity evidence SHA256SUMS | 57 entries: все SHA-256 совпали | Не доказывает текущее live состояние машины. |
| Existing unittest discovery | 80 записей: 71 PASS, 2 FAIL, 6 ERROR, 1 SKIP | Все 8 проблем связаны с отсутствующими packet dependencies/fixtures; не утверждение о 8 доказанных code regressions. |
| Independent diagnostic probes | 32/32 observations reached; 0 harness errors; P20 positive control | 31 gap/adverse observations сгруппированы по structural roots; это не 31 независимый баг и не qualification PASS. |
| Rev58 structural load | validate_ledger(..., verify_files=False): PASS | Physical canonical files/product checkout отсутствуют в packet; full live validator не выполнялся. |
| Rev58 specialized contract guard | FAIL: self-produced input T02 ARCHITECTURE; ещё 8 tickets с тем же классом | New publication guard работает, legacy admitted state не согласован с ним. |
| Runtime/source parity | Included runtime schema соответствует source schema | Полного установленного runtime ledger.py нет; полная parity не подтверждена. |

Официальный запуск: `PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v`. Время в журнале — 270.778 секунды. Не воспроизводятся missing `experiments.v104_lifecycle_qualification`, `experiments.v1_40_ticket_qualification`, `tools.dashboard`, `upstream/autopilot/tools/sync.py`, `experiments/fixtures/e03m/seed-repo`. Пять ERROR — import placeholders, поэтому 80 нельзя выдавать за 80 полноценно исполненных test bodies. Один opt-in production checkpoint test пропущен штатно.

**Две разные проблемы с fixtures не смешиваются:** неполнота supplied skill test packet — ограничение этого аудита; external evaluation-v2 resources у Worker05 — отдельный blocker в product run, известный по его return/receipts. Один не доказывает причину другого.

Диагностические fixtures начинают с явно созданного минимального legal READY state и настоящего disposable Git repository; далее используются unmodified CLI handlers. Они доказывают конкретные accepted transitions, но не заменяют полный BOOT→G6 qualification. Проба P23 проверяет непосредственно production reader `stored_payload`. Ни source Python, ни оригинальные ZIP, ни frozen Idea Scout ledger не исправлялись.

### 1.2. Наиболее опасные подтверждённые результаты

| Класс | Короткая трасса | Доказательство |
| --- | --- | --- |
| Immutable verdict bypass | ingest BLOCK → conflicting PASS ingest rejects → integrate(PASS) succeeds → INTEGRATED + review_result BLOCK | P06; source/tools/ledger.py:2842–2939 |
| Effect recovery dead end | prepared → real Git commit → reconcile applied → candidate rejects already-applied op | P03; 2209–2260, 2595–2654 |
| Continuation dead end | CONT candidate → repair BLOCK/files=[] → close rejects previous non-DONE | P21; 3147–3346 |
| False PASS | PASS coverage + failed independent check → accepted review/integration | P07; 1434–1464 |
| Control bypass | cancel request QUIESCING → dispatch accepted; CANCELLED → recover RECOVERING | P04/P05; 1953–2045, 5004–5037 |
| Failed command modifies history | stale-owner amend rejects, но canonical file уже перезаписан | P27; 4808–4870 |
| Manual BLOCK loses repair targets | import-manual BLOCK with finding → no durable findings/issues, old wait action | P29; 3896–4013 |
| Current state disagrees with own guard | rev58 structural PASS; specialized input/output binding FAIL on 9 current tickets | Frozen rev58 + validate_ticket_contract_bindings |

## 2. Reconstructed state machine

### 2.1. Система фактически является произведением нескольких состояний

Run имеет `phase ∈ PREFLIGHT, INTENT, DESIGN, PLAN, EXECUTE, VERIFY, ACCEPT` и отдельный `control ∈ ACTIVE, QUIESCING, PAUSED, BLOCKED, RECOVERING, ACCEPTED, FAILED, CANCELLED`. Ticket хранит `PLANNED, READY, RUNNING, CANDIDATE, REVIEW, INTEGRATED, BLOCKED, REPAIR, STALE, CANCELLED`. Attempt допускает `PREPARED, DISPATCHED, RETURNED, LOST, INTERRUPTED`, а его lease — отдельное состояние. Worker return status (`DONE/BLOCKED/FAILED/HANDOFF`) не является ни ticket status, ни run terminal status. Поэтому `worker FAILED` не означает terminal run `FAILED`.

В коде `REPAIR` читается как допустимое входное состояние, но обычная authorization сразу делает `READY`; отдельного необходимого durable `REVIEW→REPAIR` шага нет. `DISPATCHED` поддерживается схемой/guards, но helper не содержит отдельной команды, записывающей observed native dispatch/handle. `dispatch` регистрирует `PREPARED`, а сама модель/процесс запускаются вне helper. Это документированная граница ответственности, а не повод ожидать spawn от Python.

**Отдельного `current_candidate` нет.** Candidate SHA/tree находятся на worker attempt, а ticket.current_attempt перемещается на новый repair до появления у него candidate. Именно поэтому no-change closure вынужден искать и восстанавливать прежний attempt. Lease `active` у RETURNED worker часто является reservation candidate/worktree, а не доказательством живого writer. Следовательно, сама active lease Worker05 в rev58 — не достаточное доказательство leak; проблема — неполная таблица её безопасного disposal/reuse.

Источники: `source/schemas/contracts.schema.json` (ticket/attempt/lifecycle/lease definitions); `source/tools/ledger.py:1953–2208, 2209–2260, 3147–3346`; `source/SKILL.md:18, 70–121`.

### 2.2. Основной и альтернативные маршруты

```text
init → initial intent → requirements/design bundle
     → registered G2 coverage → registered G3 plan → EXECUTE
     → ready-ticket → dispatch[PREPARED] → native spawn/wait [вне helper]
       ├─ malformed/stale → not ingested → correct/interrupt/re-request
       ├─ LOST/INTERRUPTED → lease released with stop proof OR quarantined
       └─ valid worker return[RETURNED]
           ├─ DONE → actual audit → prepared Git effect → commit/receipt
           │       → candidate → separate immutable review
           │         ├─ BLOCK → accepted findings → authorize repair → new worker
           │         ├─ UNVERIFIABLE → missing oracle/isolation/evidence resolution
           │         └─ all required PASS → integrate → next ticket / wave / G4
           ├─ BLOCKED(files=[]) → current narrow close → previous DONE candidate
           ├─ BLOCKED/HANDOFF(nonempty; external cause; owned audit)
           │       → preserve CONTINUATION [still BLOCKED]
           │       → review / authorized repair → ordinary DONE path only later
           └─ undeclared/out-of-zone/unknown changes → quarantine
                   → only narrow legacy reconciliation currently implemented

G4 → final G5 [user-assisted qualified transport] → PASS → G6 → ACCEPTED
                         └─ BLOCK → repair wave → fresh G5 [incomplete in code]

pause/cancel/amend → QUIESCING → stop + audit + reconcile → PAUSED/BLOCKED/CANCELLED
restart → RECOVERING → actual-state reconciliation → earliest valid gate
terminal predecessor → explicit new scope + successor namespace [not reopen]
```

Этот рисунок разделяет документированный маршрут и реальные пробелы: arrows через recovery/manual repair не означают, что v1.0.11 уже умеет пройти их все. Точные ограничения ниже.

### 2.3. Реальные preconditions, durable effects и recovery каждого command family

#### T01. `init`

| Аспект | Фактическое поведение |
| --- | --- |
| Входные условия | Execution root существует; нет same namespace; сканируется другой nonterminal run в control root. |
| Durable поля | revision=0; owner/epoch=0; settings; repository; lifecycle=PREFLIGHT/ACTIVE. |
| Lease | Нет attempts/leases. |
| Candidate linkage | Нет. |
| Finding lifecycle | Нет. |
| next_action | preflight |
| Terminal/nonterminal | Run nonterminal. |
| Recovery / соседний риск | Повтор init отклоняется; читать status/recover. Не автоматическое successor inheritance. |
| Source | source/tools/ledger.py:1666–1705 |

#### T02. `publish-intent`

| Аспект | Фактическое поведение |
| --- | --- |
| Входные условия | PREFLIGHT/INTENT; no current intent; ACTIVE/BLOCKED/RECOVERING; CAS. |
| Durable поля | Canonical initial document, intent hash, revision+1, phase INTENT, runtime usage. |
| Lease | Не меняет existing leases. |
| Candidate linkage | Не создаёт. |
| Finding lifecycle | Existing issue_refs сохраняются. |
| next_action | g1_build / resolve_blockers_before_g1 / finish_recovery_then_g1 |
| Terminal/nonterminal | Nonterminal. |
| Recovery / соседний риск | Same-byte orphan document допустим до публикации; повтор уже состоявшегося initial binding запрещён. |
| Source | source/tools/ledger.py:4014–4116 |

#### T03. `adopt-requirements / publish-requirements`

| Аспект | Фактическое поведение |
| --- | --- |
| Входные условия | Exact intent doc/hash/epoch, authorized manifest; nonterminal legacy structural bootstrap. |
| Durable поля | Requirements/criteria + hash-addressed publication/provenance; same bytes idempotent. |
| Lease | Новых нет. |
| Candidate linkage | Не меняет. |
| Finding lifecycle | Не resolves code findings. |
| next_action | Продолжение текущего phase; это не bypass G1/G2. |
| Terminal/nonterminal | Nonterminal migration. |
| Recovery / соседний риск | Conflicts BLOCK; новую историю не угадывает. |
| Source | source/tools/ledger.py:4117–4213 |

#### T04. `publish-design-bundle / publish-design`

| Аспект | Фактическое поведение |
| --- | --- |
| Входные условия | DESIGN; complete immutable bundle; current intent; early self-input guard; stopped publication leases; republish лишь design-repair eligibility. |
| Durable поля | Documents/contracts/tickets/routes/current+historical publication, rev; old consumers invalidated on replacement. |
| Lease | Requires no incompatible active leases. |
| Candidate linkage | Не создаёт; old evidence может инвалидироваться. |
| Finding lifecycle | Design lineage invalidation, не general code finding projection. |
| next_action | Current-design review preparation. |
| Terminal/nonterminal | Nonterminal. |
| Recovery / соседний риск | После EXECUTE простой backward gate не обеспечивает допустимый republish; material revision path неполон. |
| Source | source/tools/ledger.py:790–903; 4231–4325; 4668–4807 |

#### T05. `prepare-design-review → ingest-return(review)`

| Аспект | Фактическое поведение |
| --- | --- |
| Входные условия | Current publication fingerprint/criteria/epoch/registration revision; identity/role. |
| Durable поля | Separate PREPARED review attempt; return stores immutable bytes, review_result, refs, review history. |
| Lease | Reviewer active→released при accepted return. |
| Candidate linkage | Subject=design publication, не Git candidate. |
| Finding lifecycle | Canonicalizes refs; historical migration отдельно. |
| next_action | await_design_review_return до результата; затем G2/G3 через gate; review ingest action может быть stale. |
| Terminal/nonterminal | Attempt RETURNED terminal, run nonterminal. |
| Recovery / соседний риск | Malformed/stale stays un-ingested; terminate/reissue; design BLOCK может вести к republish+fresh reviews. |
| Source | source/tools/ledger.py:2708–2789; 1831–1952 |

#### T06. `gate G2/G3; PLAN→EXECUTE`

| Аспект | Фактическое поведение |
| --- | --- |
| Входные условия | Current G2 coverage PASS/G3 plan PASS, matching publication; current issues absent; tickets PLANNED/READY. |
| Durable поля | phase/control/reason/next_action; snapshot. |
| Lease | Entry checks, leases не выпускает. |
| Candidate linkage | Нет нового. |
| Finding lifecycle | Global blocking issues guard. |
| next_action | Caller-supplied action, не derived enum. |
| Terminal/nonterminal | Nonterminal. |
| Recovery / соседний риск | BLOCKED plan repair→DESIGN; каждый new fingerprint требует fresh G2/G3. |
| Source | source/tools/ledger.py:4871–4968 |

#### T07. `ready-ticket`

| Аспект | Фактическое поведение |
| --- | --- |
| Входные условия | ACTIVE EXECUTE; ticket current PLANNED; dependencies INTEGRATED; criteria/contracts active. |
| Durable поля | Ticket READY; revision. |
| Lease | Не выдаёт lease; global occupancy не полностью проверяет. |
| Candidate linkage | current_attempt не candidate-entity. |
| Finding lifecycle | Не меняет. |
| next_action | Dispatch readiness; actual dispatch отдельный. |
| Terminal/nonterminal | Nonterminal. |
| Recovery / соседний риск | Contract/criterion BLOCK требует scope decision; общий validator не ловит legacy self-input. |
| Source | source/tools/ledger.py:2046–2071 |

#### T08. `dispatch`

| Аспект | Фактическое поведение |
| --- | --- |
| Входные условия | Ticket READY; worker identity/epoch, serial checks, dependencies; optional route validation; effective lease; repair authorization/signature. Run control не проверяется единообразно. |
| Durable поля | Attempt PREPARED; packet/hash, base, repair auth/provenance, ticket RUNNING/current_attempt=new. |
| Lease | Active worker lease. PREPARED не доказывает native spawn. |
| Candidate linkage | Old candidate лишь на прежнем attempt; pointer переезжает на нового без candidate. |
| Finding lifecycle | Authorization consumed производно по attempt; finding не resolved. |
| next_action | await_worker_return |
| Terminal/nonterminal | Attempt/run nonterminal. |
| Recovery / соседний риск | Exact bytes replay no new revision, но response не различает разрешение spawn; lost→terminate/reconcile. |
| Source | source/tools/ledger.py:1953–2045 |

#### T09. `validate-return; validate; audit-write-set`

| Аспект | Фактическое поведение |
| --- | --- |
| Входные условия | Read-only schema/state-bound checks или actual filesystem audit; это разные уровни. |
| Durable поля | Authoritative ledger не меняется. |
| Lease | Не выдаёт/release. |
| Candidate linkage | Не создаёт. |
| Finding lifecycle | Не создаёт. |
| next_action | Не меняет. |
| Terminal/nonterminal | Нет transition. |
| Recovery / соседний риск | Reject incomplete/stale/malformed; одного validate недостаточно для later commands. |
| Source | source/tools/ledger.py:1479–1626; 1792–1830; 2983–3146; 3717–3727 |

#### T10. `ingest-return(worker DONE)`

| Аспект | Фактическое поведение |
| --- | --- |
| Входные условия | Exact inbox/run/attempt/hash/epoch, criteria/check semantics, declared write-set; ticket_id check отсутствует. |
| Durable поля | Attempt RETURNED, immutable return_ref; ticket обычно остаётся RUNNING. |
| Lease | Worker lease остаётся active reservation; declared outside-zone →quarantine. |
| Candidate linkage | Candidate ещё нет. |
| Finding lifecycle | Worker issues appended, если представлены; DONE blocking issue отвергается. |
| next_action | audit_worker_return_and_prepare_candidate |
| Terminal/nonterminal | Attempt execution terminal; ticket/run nonterminal. |
| Recovery / соседний риск | Actual audit/effect/candidate; если quarantined — только узкая legacy reconcile либо stop/cancel path. |
| Source | source/tools/ledger.py:1831–1952 |

#### T11. `ingest-return(worker BLOCKED/FAILED/HANDOFF)`

| Аспект | Фактическое поведение |
| --- | --- |
| Входные условия | Matching return; typed issue для BLOCKED/FAILED; handoff payload для HANDOFF. |
| Durable поля | Attempt RETURNED; ticket BLOCKED; run BLOCKED; issues. |
| Lease | Обычно active; outside-zone quarantine. |
| Candidate linkage | Candidate не создаётся. |
| Finding lifecycle | Blocker сохраняется; HANDOFF не равен DONE. |
| next_action | triage_or_repair |
| Terminal/nonterminal | Attempt returned, run nonterminal. |
| Recovery / соседний риск | files=[] repair+prior DONE →close; nonempty authorized external blocker→preserve; иные комбинации часто тупик. |
| Source | source/tools/ledger.py:904–962; 1831–1952 |

#### T12. `terminate-attempt`

| Аспект | Фактическое поведение |
| --- | --- |
| Входные условия | PREPARED/DISPATCHED only; evidence; release требует PASS+writer_stopped. |
| Durable поля | LOST/INTERRUPTED; typed termination issue; ticket/run BLOCKED. |
| Lease | released с stop proof иначе quarantined. |
| Candidate linkage | Existing pointer может остаться lost attempt без candidate. |
| Finding lifecycle | Новый blocking orchestration issue. |
| next_action | recover_attempt |
| Terminal/nonterminal | Attempt terminal; run nonterminal. |
| Recovery / соседний риск | Generic returned-attempt closure отсутствует; quarantined lost не принимает legacy reconcile. |
| Source | source/tools/ledger.py:2176–2208 |

#### T13. `prepare-effect`

| Аспект | Фактическое поведение |
| --- | --- |
| Входные условия | CAS; новый либо exact matching op ID; unrestricted typed kind string. |
| Durable поля | Operation prepared,target,expected_before,intended_after,authority; snapshot. |
| Lease | Не меняет. |
| Candidate linkage | Не меняет. |
| Finding lifecycle | Не меняет. |
| next_action | apply_prepared_effect |
| Terminal/nonterminal | Nonterminal. |
| Recovery / соседний риск | Crash requires reconcile; replay abandoned/uncertain misleadingly returns prepared. |
| Source | source/tools/ledger.py:2574–2594 |

#### T14. `candidate`

| Аспект | Фактическое поведение |
| --- | --- |
| Входные условия | Returned worker DONE; active lease; prepared candidate_commit op; minimal receipt PASS+SHA. |
| Durable поля | Candidate sha/tree на attempt; ticket CANDIDATE; op applied/receipt_ref. |
| Lease | Worker active reservation сохранена. |
| Candidate linkage | current candidate не отдельный record; full Git proof weaker than preserve. |
| Finding lifecycle | Не closes findings. |
| next_action | review_change |
| Terminal/nonterminal | Nonterminal. |
| Recovery / соседний риск | Applied effect without linkage cannot use candidate; forged/minimal receipt accepted. |
| Source | source/tools/ledger.py:2209–2260 |

#### T15. `preserve-blocked-candidate`

| Аспект | Фактическое поведение |
| --- | --- |
| Входные условия | Current BLOCKED returned worker; active lease; nonempty exact audited write-set; owner auth; focused checks pass; all failures external/out-of-scope; strict base/tree/provenance. |
| Durable поля | Continuation receipt/auth applied/candidate sha/tree/operation applied; original return unchanged. |
| Lease | Active reservation сохраняется. |
| Candidate linkage | CONTINUATION stored on worker; ticket/run remain BLOCKED. |
| Finding lifecycle | External blocker сохранён. |
| next_action | review_or_repair_continuation_candidate |
| Terminal/nonterminal | Nonterminal; не интегрируемый DONE. |
| Recovery / соседний риск | Review/authorized repair; repeated preserve supported narrowly; subsequent no-change repair closure broken. |
| Source | source/tools/ledger.py:2261–2573 |

#### T16. `prepare-review → ingest-return(review)`

| Аспект | Фактическое поведение |
| --- | --- |
| Входные условия | Candidate frozen/current, packet subject, criteria/axes semantics; continuation allowed; prepare epoch gap; authoritative barrier необязателен в ingest. |
| Durable поля | Separate review PREPARED then RETURNED; reviews/findings/issues; ticket REVIEW or continuation BLOCKED. |
| Lease | Reviewer active→released; worker reservation сохранена. |
| Candidate linkage | Review pinned SHA; ticket.current_attempt остаётся worker. |
| Finding lifecycle | PASS/BLOCK/UNVERIFIABLE; current binding missing possible. |
| next_action | await_review_return / await_blocked_candidate_review; после обычного ingest часто stale. |
| Terminal/nonterminal | Review attempt terminal; ticket nonterminal. |
| Recovery / соседний риск | BLOCK→authorize; malformed→correct payload/stop/reissue; integrity failure must not be ingested. |
| Source | source/tools/ledger.py:1434–1530; 1831–1952; 2655–2707 |

#### T17. `authorize-repair`

| Аспект | Фактическое поведение |
| --- | --- |
| Входные условия | REVIEW/BLOCKED/REPAIR or narrow READY rebind; accepted blocking ticket-bound record; single contract; provenance only in special cases. |
| Durable поля | Decision authorized; finding.repair_contract_ref; ticket READY; optional old auth invalidation. |
| Lease | Same-ticket released if not in-flight/quarantined, без общего stop evidence requirement. |
| Candidate linkage | current_attempt остаётся previous worker. |
| Finding lifecycle | Не resolves; only one finding selected. |
| next_action | dispatch_repair / dispatch_repair_with_blocker_retained |
| Terminal/nonterminal | Nonterminal. |
| Recovery / соседний риск | Missing source legacy rebind поддержан; unchanged/other incompatible READY auth — не general revoke/replan. |
| Source | source/tools/ledger.py:981–1428; 2072–2175 |

#### T18. `close-blocked-attempt`

| Аспект | Фактическое поведение |
| --- | --- |
| Входные условия | Current returned repair BLOCKED/files=[]; active lease; no candidate/effect; exact clean previous base; prior returned released DONE candidate. |
| Durable поля | Closure receipt/decision; current_attempt restored previous worker; ticket/run BLOCKED. |
| Lease | Blocked attempt lease released. |
| Candidate linkage | Только previous DONE, не CONTINUATION. |
| Finding lifecycle | Scope issue остаётся; new auth needed. |
| next_action | authorize_repair |
| Terminal/nonterminal | Attempt safely disposed, ticket nonterminal. |
| Recovery / соседний риск | No generalization for implement/HANDOFF/FAILED/previous continuation; replay after progress may fail. |
| Source | source/tools/ledger.py:3147–3346 |

#### T19. `reconcile-quarantined-attempt`

| Аспект | Фактическое поведение |
| --- | --- |
| Входные условия | Exact returned repair DONE, quarantined legacy create→modify mismatch; owner actor/finding/prior/base/audit, current pointer. |
| Durable поля | Receipt+decision, reconciled lease/provenance, invalidated exact write-set issue. |
| Lease | quarantined→active reservation. |
| Candidate linkage | Candidate ещё отдельным candidate command. |
| Finding lifecycle | Только доказанный legacy mismatch reconciled. |
| next_action | prepare_candidate_effect |
| Terminal/nonterminal | Nonterminal. |
| Recovery / соседний риск | Other quarantine rejected; no bypass uncertain liveness. Replay после дальнейшего release не stable. |
| Source | source/tools/ledger.py:3347–3716 |

#### T20. `reconcile-effect`

| Аспект | Фактическое поведение |
| --- | --- |
| Входные условия | Только operation prepared; result applied/uncertain/unchanged; optional receipt fields. |
| Durable поля | Operation applied / uncertain / abandoned; limited observed Git checks. |
| Lease | Не даёт general target reuse guard. |
| Candidate linkage | Не публикует candidate linkage. |
| Finding lifecycle | uncertain sets BLOCKED. |
| next_action | resume_after_reconciled_effect / reconcile_uncertain_effect / decide_effect_retry |
| Terminal/nonterminal | Nonterminal или completed effect. |
| Recovery / соседний риск | uncertain cannot re-enter; applied candidate cannot candidate(); abandoned same ID not rearmed. |
| Source | source/tools/ledger.py:2595–2654 |

#### T21. `adjudicate`

| Аспект | Фактическое поведение |
| --- | --- |
| Входные условия | Typed reason/evidence; conflicting review refs либо disagreement issue. |
| Durable поля | Decision; issue disposition/decision_ref; control. |
| Lease | Не закрывает subject writer/reviewer. |
| Candidate linkage | Candidate unchanged assumed, not full currentness projection. |
| Finding lifecycle | PASS removes disagreement from lifecycle.issue_refs, но impact blocking остаётся. |
| next_action | continue_after_adjudication / repair_or_user_decision |
| Terminal/nonterminal | Nonterminal. |
| Recovery / соседний риск | Следующий gate может опять блокироваться тем же issue. |
| Source | source/tools/ledger.py:2790–2841 |

#### T22. `integrate`

| Аспект | Фактическое поведение |
| --- | --- |
| Входные условия | Nonmanual review PREPARED/RETURNED; supplied PASS; selected candidate matches linked worker; minimal integrity receipt; continuation direct excluded. |
| Durable поля | Ticket INTEGRATED; selected review record/return_ref; issues/finding invalidation частична. |
| Lease | Selected reviewer + linked worker released, другие review leases не aggregate guarded. |
| Candidate linkage | Current worker SHA retained as integrated, no actual Git landing action inside helper. |
| Finding lifecycle | Можно overwrite accepted BLOCK; broad issue invalidation vs single finding. |
| next_action | Может оставаться stale; явно не recomputed в normal completion. |
| Terminal/nonterminal | Ticket terminal-for-current-scope, run nonterminal. |
| Recovery / соседний риск | Current multiple axes/blockers не uniformly checked; new candidate repair review needed; amendment makes stale. |
| Source | source/tools/ledger.py:2842–2939 |

#### T23. `prepare-handoff`

| Аспект | Фактическое поведение |
| --- | --- |
| Входные условия | Review/acceptance packet+full projection, frozen candidate, current intent; bundle/export disjoint. |
| Durable поля | Export manifest, packet/projection/checklist; existing attempt mode→user_assisted/PREPARED. |
| Lease | Lease не получает отдельный proof of writer stop. |
| Candidate linkage | Pinned fingerprint сохранён. |
| Finding lifecycle | Не создаёт. |
| next_action | import_manual_review; BLOCKED/manual_review_pending |
| Terminal/nonterminal | Nonterminal real user checkpoint. |
| Recovery / соседний риск | New manual return; packet review-kind can become unimportable as acceptance; no exact idempotency. |
| Source | source/tools/ledger.py:3787–3895 |

#### T24. `import-manual`

| Аспект | Фактическое поведение |
| --- | --- |
| Входные условия | User-assisted review, intent/packet/env/context/manifest/ledger baseline; acceptance packet only; current attempt state/owner epoch guard incomplete. |
| Durable поля | Acceptance record+evidence; returned/released reviewer; PASS→ACCEPT ACTIVE, maybe ticket INTEGRATED. |
| Lease | Worker lease при per-ticket use остаётся active. |
| Candidate linkage | Candidate argument equals packet; no unified final candidate generation obligation. |
| Finding lifecycle | Payload BLOCK findings не appended в durable findings/issues; outcome_refs empty. |
| next_action | PASS g6_final_record; BLOCK старый import_manual_review. |
| Terminal/nonterminal | Review terminal; run nonterminal. |
| Recovery / соседний риск | Manual BLOCK не даёт штатных repair targets; critical-axis vs final G5 purpose смешаны. |
| Source | source/tools/ledger.py:3896–4013 |

#### T25. `gate G4/G6`

| Аспект | Фактическое поведение |
| --- | --- |
| Входные условия | G4 current tickets INTEGRATED/no global blockers/no leases/effects; G6 ACCEPT+latest current-intent G5 PASS+closures. |
| Durable поля | Phase/control; snapshot. |
| Lease | Must be closed; gate не закрывает их. |
| Candidate linkage | G6 lacks own mandatory current candidate generation comparison. |
| Finding lifecycle | Global blocking issue predicate, не lifecycle.issue_refs only. |
| next_action | Caller-supplied; G6 terminal action. |
| Terminal/nonterminal | G6→ACCEPTED terminal, G4 nonterminal. |
| Recovery / соседний риск | Stale issue projection creates gate deadlock; accepted run must not reopen. |
| Source | source/tools/ledger.py:4871–4968 |

#### T26. `amend`

| Аспект | Фактическое поведение |
| --- | --- |
| Входные условия | Authority text, current intent, duplicate checks внутри transaction; canonical write происходит раньше fence. |
| Durable поля | New intent/invalidation closure; tickets STALE; attempts invalidated; phase INTENT ACTIVE. |
| Lease | PREPARED/DISPATCHED quarantined, но не остановлены процессно. |
| Candidate linkage | Old candidates historical/stale. |
| Finding lifecycle | All affected records invalidated, broad closure. |
| next_action | g1_recheck with quiesce as textual precondition. |
| Terminal/nonterminal | Должен быть nonterminal; common guard отсутствует. |
| Recovery / соседний риск | Same canonical version stale call may corrupt bytes before rejection; нужна storage/transition hardening. |
| Source | source/tools/ledger.py:4808–4870 |

#### T27. `gate QUIESCING/PAUSED; cancel request/finalize`

| Аспект | Фактическое поведение |
| --- | --- |
| Входные условия | Pause требует QUIESCING+no leases/effects; cancel finalize PASS writers_stopped/reconciled and no prepared/uncertain effects. |
| Durable поля | QUIESCING then PAUSED/CANCELLED; pending attempts interrupted, unfinished tickets cancelled. |
| Lease | Finalize releases active/quarantined; evidence not retained as immutable ref. |
| Candidate linkage | Частичные изменения не reset/revert; candidates history сохраняется. |
| Finding lifecycle | History сохраняется; no product rollback. |
| next_action | stop_reconcile_then_cancel / terminal_cancelled |
| Terminal/nonterminal | CANCELLED terminal, PAUSED nonterminal. |
| Recovery / соседний риск | Dispatch всё ещё может после request; no implicit destructive cleanup; successor explicit. |
| Source | source/tools/ledger.py:4871–5003 |

#### T28. `recover`

| Аспект | Фактическое поведение |
| --- | --- |
| Входные условия | Current либо verified prev/snapshot; owner token, optional takeover/attestation. |
| Durable поля | RECOVERING/reconcile_actual_state; epoch++ при takeover; new revision. |
| Lease | Takeover quarantines in-flight only; returned active reservation needs separate audit. |
| Candidate linkage | Pointers from selected snapshot, actual Git не автоматически reconciled. |
| Finding lifecycle | Не делает general resolution. |
| next_action | reconcile_actual_state |
| Terminal/nonterminal | Current code reopens even CANCELLED (defect). |
| Recovery / соседний риск | Далее узкие reconciliation commands; malformed/unknown schema diagnose read-only. |
| Source | source/tools/ledger.py:5004–5037 |

#### T29. `migrate-review-currentness`

| Аспект | Фактическое поведение |
| --- | --- |
| Входные условия | Nonterminal; fresh current design coverage+plan PASS; exact publication lineage. |
| Durable поля | Audited migration/provenance and targeted invalidations. |
| Lease | Не может auto-release product writers. |
| Candidate linkage | Не является migration code candidate lineage. |
| Finding lifecycle | Historical design chains only; ambiguous remain blocking. |
| next_action | Current design continuation. |
| Terminal/nonterminal | Nonterminal migration. |
| Recovery / соседний риск | Не использовать для 7 historical T02 code findings без расширенного protocol. |
| Source | source/tools/ledger.py:4373–4654 |

#### T30. `status / brief / render-view / diagnose; publish-usage`

| Аспект | Фактическое поведение |
| --- | --- |
| Входные условия | Read projections; usage publishing имеет отдельный CAS event. |
| Durable поля | Views outside authority; usage counters/traces only. |
| Lease | Не меняет authorization лизов. |
| Candidate linkage | Не authoritative candidate transition. |
| Finding lifecycle | Не resolves. |
| next_action | Проецирует stored next_action, в v1.0.11 возможен stale. |
| Terminal/nonterminal | No lifecycle transition. |
| Recovery / соседний риск | Refresh view не исправляет ledger consistency; allowed terminal telemetry надо явно whitelist. |
| Source | source/tools/ledger.py:1706–1830 |

### 2.4. Где документация сильнее реализации

`source/design/02-run-ledger-and-artifacts.md` отдельно называет compound intent-level CLI и ≤4 calls **design target, не frozen API**. Поэтому отсутствие трёх compound commands само по себе не объявляется багом. Но state/evidence/safety свойства, требуемые `SKILL.md` и phase-инструкциями, всё равно должны сохраняться при реальной последовательности более мелких команд.

`phases/execute.md` требует actual audit, immutable review, обязательный risk axis и integrity barrier. `candidate` не требует такой же actual proof, как `preserve-blocked-candidate`; `ingest-return(review)` не требует barrier receipt; `integrate` не объединяет required reviews. Это доказанные mechanical enforcement gaps, даже если аккуратный оркестратор может вручную соблюдать более сильный протокол.

`phases/recover.md` требует не дублировать unknown effects/spawns и не терять partial state. `reconcile-effect` сам производит unsupported uncertain/applied combinations. `phases/accept.md` описывает repair wave после manual G5 BLOCK, но `import-manual` не создаёт repairable findings. `SKILL.md` запрещает self-produced input contracts, но legacy rev58 остаётся несовместимой с этим guard.

**Semi-mode:** routine decisions и обычный repair не требуют per-ticket user approval. Реальные checkpoints — explicit requested spec/plan/final checkpoint, material ambiguity, cost/credential/irreversible/scope/oracle authority, manual critical/G5 setup, квалифицированная owner attestation при recovery. Это следует из `SKILL.md:10–14,70–80` и `design/01-lifecycle-state-machine.md:108–110`. Нельзя чинить await-loop, превращая каждый dispatch в просьбу «продолжить»; нельзя и убрать manual critical barrier под видом full/semi автономности.

## 3. Audit известных incidents A–L

### A. Contract binding lifecycle

**Root cause / подтверждение:** Подтверждён для predecessor: rev119→120 показывает поздний блок; self-produced/proposed relation видна в snapshot. Новые design_bundle теперь имеют early guard.

**Статус v1.0.11:** Частично. Новый publish/gate guard есть; rev58 всё ещё содержит 9 self-input current tickets с active contracts и проходит общий validator. Не доказано, какой старый entry point их первоначально допустил.

**Остаточный риск:** P0; связанные структурные findings: AH-08.

**Обязательные соседние сценарии:** Legacy load→ready/dispatch; active self-input; specification-input vs deliverable-output; successor inheritance.

### B. Worker dispatch / await

**Root cause / подтверждение:** Инструкции явно исправлены: wait внутренний, bounded intervals и stop reconciliation. В packet нет полного native spawn/wait trace, поэтому фактическое поведение живого runtime независимо не подтверждено.

**Статус v1.0.11:** Instruction-level fix есть; гарантия выполнения и корректного restart отсутствует. Helper не держит agent loop и не подтверждает native handle.

**Остаточный риск:** P1; связанные структурные findings: AH-06, AH-11.

**Обязательные соседние сценарии:** Quota/context cutoff; 3 no-progress waits; READY before spawn; unknown handle; child tools после interrupt; stale next_action.

### C. create → repair modify

**Root cause / подтверждение:** Подтверждён packet/return Worker02, reconciliation audit и create-only исходной lease; код содержит guarded expansion.

**Статус v1.0.11:** Узкий путь исправлен, но контракт не един: general modify bypasses source/base/deny; source review допускается не всеми следующими командами.

**Остаточный риск:** P0; связанные структурные findings: AH-02, AH-03.

**Обязательные соседние сценарии:** Create→modify→preserve hop; ordinary modify stale base; source review→BLOCK preserve; allow/deny overlap.

### D. Quarantined attempt recovery

**Root cause / подтверждение:** Rev33 и worker02 reconciliation receipt подтверждают реальный guarded legacy reconciliation.

**Статус v1.0.11:** Исправлен ровно legacy returned DONE create→modify случай. Остальные quarantine intentionally block, но общего proof-carrying выхода в том же ticket нет.

**Остаточный риск:** P0; связанные структурные findings: AH-03.

**Обязательные соседние сценарии:** LOST/INTERRUPTED quarantine с новым stop proof; non-DONE partial writes; reconciliation replay после lease release/integration.

### E. Transitive repair provenance

**Root cause / подтверждение:** Worker03 packet/return, auth и candidate lineage в retained snapshots подтверждают последующий modify. Точного standalone rev37 и старого кода нет.

**Статус v1.0.11:** Транзитивный path validator существует. Но admission не универсален, preserve hops/source normalization и general candidate проверяются разными контрактами.

**Остаточный риск:** P0; связанные структурные findings: AH-02, AH-03.

**Обязательные соседние сценарии:** Промежуточный repair не трогал ранее created path; несколько preserve hops; fork candidate; old finding на новом modify candidate; publication после stale source.

### F. BLOCKED no-change attempt

**Root cause / подтверждение:** Worker04 return files=[] и rev48 closure receipt прямо подтверждают release lease и восстановление Worker03.

**Статус v1.0.11:** Узкий repair→BLOCKED→previous DONE исправлен. Initial BLOCK/HANDOFF, FAILED и previous CONTINUATION не покрыты.

**Остаточный риск:** P0; связанные структурные findings: AH-03.

**Обязательные соседние сценарии:** Continuation→repair→no-change BLOCK; first attempt без candidate; replay closure после следующего dispatch.

### G. Undispatchable repair authorization

**Root cause / подтверждение:** Rev49 defective auth05 и rev50 source-bound auth06 позволяют независимо проверить missing source и supersession.

**Статус v1.0.11:** Исправлена конкретная missing-source ветка. P12 даёт новую accepted auth с unchanged signature, которую dispatch гарантированно отвергает.

**Остаточный риск:** P0; связанные структурные findings: AH-02.

**Обязательные соседние сценарии:** Unchanged retry; full packet zone заранее неизвестна; modify-zone invalid source/base; unused auth cancel/revoke/rebind.

### H. BLOCKED/HANDOFF с полезным непустым write-set

**Root cause / подтверждение:** Worker05 return, rev53→54 и continuation receipt подтверждают корректное сохранение exact owned changes с retained blocker.

**Статус v1.0.11:** Сам preserve переход строгий и полезный. Lifecycle вокруг него не замкнут: P21/P22; нет общего завершения/снятия external debt.

**Остаточный риск:** P0; связанные структурные findings: AH-03, AH-05.

**Обязательные соседние сценарии:** Continuation→no-change repair; source review; repeated continuation; repair DONE при неразрешённом external blocker; crash между effect/receipt/linkage.

### I. Review finding binding

**Root cause / подтверждение:** Три current findings review05 имеют только criteria/contracts/requirements refs; attempt subject=T02-R17. Ingest проходит, authorize отвергает. P01 воспроизводит root cause.

**Статус v1.0.11:** Не исправлен. Сам subject известен, но canonicalization добавляет его только при некоторых формах reported refs.

**Остаточный риск:** P0; связанные структурные findings: AH-01.

**Обязательные соседние сценарии:** Все refs глобальные; refs packet-local; conflicting/foreign ticket; empty refs; rebind exact old return без re-ingest.

### J. Stale next_action

**Root cause / подтверждение:** Rev57→58: review05 PREPARED→RETURNED/BLOCK, reviewer lease released, но action остаётся await_blocked_candidate_review. В generic probe остаётся await_review_return.

**Статус v1.0.11:** Не исправлен. Это не только dashboard: persisted continuation предлагает ожидать уже принятый результат.

**Остаточный риск:** P0; связанные структурные findings: AH-01, AH-06.

**Обязательные соседние сценарии:** PASS, BLOCK, UNVERIFIABLE; manual BLOCK; integrate; adjudication; duplicate return после restart.

### K. Historical vs actionable findings

**Root cause / подтверждение:** В ledger 21 findings: 10 T02 code-review = 3 current+7 historical; остальные 11 — design. Все 10 code records без invalidated_by; 17 blocking issues.

**Статус v1.0.11:** Глубже отсутствия view: currentness/invalidations/issue mirroring неоднозначны. Existing migration касается design publications, не code-candidate lifecycle.

**Остаточный риск:** P0; связанные структурные findings: AH-01.

**Обязательные соседние сценарии:** Старый unresolved finding после нового candidate; перенос verification debt; broad fresh review vs targeted resolution; mirrored issue без binding.

### L. Один finding → одна authorization

**Root cause / подтверждение:** CLI/schema/active_repair_authorization поддерживают singular finding_ref; aggregate review_verdict issue может быть одной ссылкой, но не даёт individual closure всех findings.

**Статус v1.0.11:** Групповой audited repair как first-class переход отсутствует. Требовать 3 worker cycles при одном связанном изменении из файлов не следует.

**Остаточный риск:** P0; связанные структурные findings: AH-01, AH-09.

**Обязательные соседние сценарии:** 3 findings одного candidate→one scope→one worker→three verified outcomes; conflict scopes; partial resolution; G5 repair wave.

Historical fixes не переисполнялись на исходных v1.0.6–v1.0.10 binaries: пакет содержит текущий source и release documents, а не всю историю executable source. Там, где отсутствует отдельная fault revision, вывод опирается на точные соседние snapshots/returns/receipts и явный current guard. Release notes сами по себе не принимались за доказательство closure.

## 4. Новые findings и проверенные structural risks

| ID | Priority | Structural finding | Primary executed probes |
| --- | --- | --- | --- |
| AH-01 | P0 | Finding lifecycle: subject binding, current projection и групповой repair | P01, P24, P28 |
| AH-02 | P0 | Authorize/dispatch/return используют несовпадающий admission contract | P09, P10, P11, P12, P19, P24 |
| AH-03 | P0 | Неполный lifecycle попытки и continuation candidate | P13, P15, P18, P21, P22 |
| AH-04 | P0 | Review/integrate могут обойти immutable verdict и обязательные review barriers | P06, P07, P08, P16, P17 |
| AH-05 | P0 | Effect journal не замкнут и general candidate слабее continuation candidate | P02, P03, P14, P26 |
| AH-06 | P0 | Нет единого phase/control/terminal/owner precondition для mutators | P04, P05, P19, P31 |
| AH-07 | P0 | Immutable evidence/canonical publication не защищены единообразно | P23, P27 |
| AH-08 | P0 | Legacy admitted state сохраняет self-produced input contracts после исправления публикации | Frozen/static/official suite |
| AH-09 | P0 | Manual critical/G5 transport не замкнут в общий review→repair lifecycle | P29, P30, P31, P32 |
| AH-10 | P1 | Successor, predecessor evidence и wave boundary не имеют единого executable closure | Frozen/static/official suite |
| AH-11 | P1 | Регистрация попытки не фиксирует наблюдаемый native spawn/wait/stop как durable protocol | Frozen/static/official suite |
| AH-12 | P1 | Qualification не доказывает closure текущей state machine и пакет неполон для воспроизведения release claims | Frozen/static/official suite |
| AH-13 | P2 | Операционные метрики и представления не отделяют регистрацию от фактического исполнения | Frozen/static/official suite |

### AH-01 — P0 — Finding lifecycle: subject binding, current projection и групповой repair

**Root cause.** Зарегистрированный subject review, reported affected refs, durable finding, mirrored issue и lifecycle.issue_refs ведутся разными правилами. Currentness определяется частично через invalidated_by, частично через current_attempt; отдельного состояния verification obligations нет. Authorization поддерживает только один finding_ref.

**Evidence.**

`source/tools/ledger.py:1011–1033; 1640–1665; 2072–2175; 2908–2926` — Ticket binding требуется позже ingest; integration инвалидирует все ticket-bound review issues, но только один finding; adjudication меняет disposition без снятия blocking impact.

`source/tools/ledger.py:1831–1952; 2790–2841` — Обычный review ingest и adjudication оставляют несогласованные action/blocker projections.

`evidence/state/successor/rev-058-ledger.json :: /findings; /issues; /lifecycle` — 21 findings всего; 10 code-review T02, из них 3 на текущем candidate; 17 blocking issues и устаревший await.

`P01_missing_ticket_binding`

`P24_historical_finding_reuse`

`P28_adjudication_blocker_projection`

**Failure modes.** Accepted review нельзя использовать для repair без ticket binding. Старый finding может снова авторизовать repair нового candidate в modify-zone. PASS adjudication оставляет blocking issue; active projection расходится с lifecycle.issue_refs. Один repair либо искусственно дробится по finding_ref, либо устраняет несколько дефектов без поэлементного audit trail. Отсутствие нового finding по старой проблеме ошибочно может трактоваться как доказанное исправление.

**Affected code/schema.** `append_review_findings`, `cmd_ingest`, `cmd_authorize_repair`, `finding_matches_candidate`, `cmd_integrate`, `cmd_adjudicate`, `cmd_migrate_review_currentness`, `schema: review_finding/repair_contract`.

**Минимальное безопасное и системное исправление.**

1. Ввести обязательный canonical subject binding {run,ticket,intent,publication,candidate-generation,review-attempt}; reported_affected_refs сохранять как raw observation, не использовать как единственный repair target.

2. Сделать ingest единым для всех review kinds; валидировать repair usability до publication. При точном одно-ticket subject допустима каноническая привязка независимо от списка глобальных refs; конфликтующий subject отвергать.

3. Хранить append-only binding/resolution/supersession events и вычислять active findings, unresolved verification obligations, mirrored issues и next_action из одной projection. Не приравнивать historical к resolved.

4. Добавить finding_refs[] в единую candidate-bound repair authorization; каждому finding — own expected_proof, target criterion, re-review outcome. Разрешать объединение только при общем candidate и согласованной lease-zone.

5. Resolution должен ссылаться на независимое подтверждение соответствующего finding. Candidate supersession не даёт blanket resolution всех прежних findings/обязательств.

6. Сделать evidence-bound recovery для уже ingested records: raw return hash и исходная история неизменны, добавляются binding events для finding и его mirrored issue.

**Regression.** Q02, Q03, Q04, Q11, Q12, Q13, Q29, Q32.

**Backward compatibility.** Существующие findings без subject и issues с несовпадающими статусами нельзя массово молча нормализовать. Нужна версия projection и миграционный receipt; ambiguous lineage остаётся BLOCKED.

**Existing-run recovery.** Для rev58 привязать ровно 3 finding-e977… к review05/candidate ef8d…; 7 старых code findings оставить историческими, с отдельным закрытием либо переносом verification obligations. Старые BLOCK verdict records и interrupted-review issue не удалять.

**Граница runtime.** Внутри skill; внешний runtime нужен только для предоставления фактических stop/isolation observations.

### AH-02 — P0 — Authorize/dispatch/return используют несовпадающий admission contract

**Root cause.** Проверки readiness, authorizations, effective lease, candidate provenance, packet identity и повторяемости распределены по командам. В effective_worker_lease ветка, полностью укладывающаяся в ticket.zone, выходит раньше проверок deny/source/current finding. Source provenance обязательна только для некоторых create→modify веток.

**Evidence.**

`source/tools/ledger.py:981–1033; 1134–1428; 1953–2175` — Неполный preflight authorization; source/deny/currentness в основном проверяются лишь при expansion.

`source/tools/ledger.py:1479–1530; 2655–2707` — Worker return не сравнивает ticket_id с registered subject; review registration принимает иной packet epoch.

`P09_allow_deny_overlap`

`P10_worker_wrong_ticket`

`P11_stale_modify_base`

`P12_undispatchable_unchanged_auth`

`P19_review_epoch_registration`

`P24_historical_finding_reuse`

**Failure modes.** Authorization READY гарантированно отвергается следующим dispatch по unchanged signature. Modify-zone принимает чужой source_attempt_ref и nonexistent/stale base. Allow/deny overlap принимается как active lease. Worker return с FOREIGN-TICKET принимается, а более строгий reader позже его не сможет использовать. Packet epoch и attempt epoch расходятся; contract criteria/risk/route не связаны единым admission proof.

**Affected code/schema.** `cmd_authorize_repair`, `cmd_dispatch`, `effective_worker_lease`, `repair_candidate_worker`, `repair_requires_transitive_create_modify_provenance`, `validate_return_against_attempt`, `cmd_prepare_review`.

**Минимальное безопасное и системное исправление.**

1. Создать canonical AttemptPlan и единый prepare/validate admission, используемый authorize и dispatch: exact subject, base/tree, epoch, intent/publication, selected findings, scope allow+deny, route/risk, criterion/check set, liveness conflicts.

2. Перед READY проверять те же детерминированные условия, что и dispatch, включая unchanged signature и source validity. Изменение внешнего состояния между командами может вызвать понятный replan, но не изначально невозможную authorization.

3. Source candidate обязателен для любого repair, не только create→modify. Разрешённый source review сначала однозначно нормализуется в producing worker/candidate identity; все последующие команды используют одинаковую нормализованную ссылку.

4. Consume/revoke/rebind authorization отдельными audited состояниями; exact same-byte retry возвращает прежнее решение, changed unused authorization оформляется новым ID с supersedes, а не редактированием объекта.

5. Проверять return kind и все поля registered identity, включая ticket_id; packet epoch должен совпадать с owner epoch уже при регистрации.

6. Проверять deny до любых ранних return; проверять пересечение checkout/common-dir/lease zones независимо от ticket.state.

**Regression.** Q02, Q03, Q10, Q14, Q15, Q25, Q26, Q27, Q30.

**Backward compatibility.** Ранее допустимые packets/auth become invalid. Не применять новые ограничения только к следующему dispatch: миграция должна заранее выявить и отозвать/перепривязать unconsumed incompatible authorizations.

**Existing-run recovery.** Rev58: auth06 уже использована Worker05 и остаётся history. Для следующего repair — новый grouped authorization с точным Worker05 candidate и свежим планом scope. Не переиспользовать auth05/06 и не менять их bytes.

**Граница runtime.** Внутри skill; внешний runtime нужен только для предоставления фактических stop/isolation observations.

### AH-03 — P0 — Неполный lifecycle попытки и continuation candidate

**Root cause.** current_attempt одновременно означает последнее исполнение, текущего writer и носителя candidate. Recovery реализовано узкими исключениями для определённых status/mode/previous-return combinations, а не общей таблицей финализации попыток и disposition файлов.

**Evidence.**

`source/tools/ledger.py:2176–2208; 2261–2353; 3147–3346; 3347–3716` — Terminate работает только для PREPARED/DISPATCHED; close-blocked — только repair/BLOCKED/files=[] с предыдущим DONE; continuation source допускает только worker.

`source/phases/recover.md:24–31` — Другие quarantines явно оставлены blocked; общего доказательного reuse transition нет.

`evidence/receipts/worker04-blocked-closure-receipt.json :: entire object` — Узкий no-change recovery реально применён.

`P13_lost_partial_create`

`P15_empty_HANDOFF_closure`

`P18_initial_nochange_BLOCK`

`P21_continuation_nochange`

`P22_review_source_preserve`

**Failure modes.** Initial no-change BLOCK/HANDOFF и returned FAILED не имеют симметричного штатного close. Continuation→repair→no-change BLOCK не восстанавливает continuation, потому что previous return обязан быть DONE. Repair dispatch принимает source review, но preserve после реального commit отвергает этот же source. Lost create с полезным partial file и без candidate нельзя безопасно продолжить как modify через обычный repair. Quarantined LOST/INTERRUPTED нельзя перевести в пригодный reuse только новой stop evidence; legacy reconcile не подходит.

**Affected code/schema.** `cmd_terminate_attempt`, `cmd_close_blocked_attempt`, `cmd_preserve_blocked_candidate`, `validate_continuation_provenance`, `cmd_reconcile_quarantined_attempt`, `ticket/attempt/candidate schema`.

**Минимальное безопасное и системное исправление.**

1. Добавить отдельный immutable candidate record и authoritative current_candidate; отделить current_worker_attempt/last_worker_attempt от candidate linkage. Continuation хранит quality=CONTINUATION и blocker debt, не фальшивый DONE.

2. Описать finalize-attempt матрицей status×write-set×writer-stop×audit×prior-candidate: no changes, owned audited changes, uncertain/out-of-zone changes. Для каждой строки — release/reservation/quarantine и точный следующий шаг.

3. Обобщить no-change closure на implement/repair и BLOCKED/HANDOFF/FAILED, когда фактическая безопасная disposition доказана. Можно сохранить предыдущий DONE либо CONTINUATION; если candidate ещё нет — retry от проверенного initial base.

4. Добавить proof-carrying reconciliation остановленных LOST/INTERRUPTED/quarantined attempts без превращения untrusted partial changes в DONE; новый worker использует проверенный snapshot либо explicitly authorized disposal.

5. Свести source normalization и транзитивные create/modify/preserve hops к общей библиотеке; проверять её при candidate publication, а не только при следующем expansion.

6. Повторы closure/preserve/reconcile после дальнейшего прогресса возвращают записанный результат операции и не требуют, чтобы mutable pointers навсегда остались в её старом post-state.

**Regression.** Q05, Q06, Q07, Q08, Q09, Q10, Q15, Q17, Q18, Q23, Q24, Q28.

**Backward compatibility.** Current_attempt legacy alias потребует migration. Нельзя просто считать active returned worker lease живым процессом либо автоматически освобождать её: это может быть reservation и требуются stop/audit observations.

**Existing-run recovery.** Worker05 и continuation receipt сохраняются. Старую lease release делать доказательно перед новым writer; следующий no-change repair должен восстанавливать ef8d… как CONTINUATION, а не искать более ранний DONE и терять полезные изменения.

**Граница runtime.** Внутри skill; внешний runtime нужен только для предоставления фактических stop/isolation observations.

### AH-04 — P0 — Review/integrate могут обойти immutable verdict и обязательные review barriers

**Root cause.** Integrate повторно ingest-ит переданный файл вместо потребления уже принятого immutable review. Semantic validators проверяют PASS coverage, но не проверяют PASS независимых checks. Acceptance of a candidate сведено к одному review, без aggregate policy по всем требуемым axes/rounds.

**Evidence.**

`source/tools/ledger.py:1434–1464; 1831–1952; 2655–2707; 2842–2939` — Conflicting duplicate ingest отвергается, но integrate имеет отдельный проход; integrity ledger hash optional; required review axis не enforced.

`source/phases/execute.md:13–17` — Документация требует independent risk axis, stopped reviewer, integrity barrier.

`source/phases/accept.md:13–19` — Для critical axis требуется user-assisted transport до отдельной qualification.

`P06_conflicting_review_integrate`

`P07_failed_check_PASS`

`P08_critical_policy_bypass`

`P16_parallel_review_BLOCK_bypass`

`P17_review_ingest_without_barrier`

**Failure modes.** Accepted BLOCK меняется на supplied PASS через integrate; review_result остаётся BLOCK, ticket становится INTEGRATED. PASS с failed check принимается и интегрируется. PASS одного review интегрируется при BLOCK другого текущего required review. Critical ticket можно интегрировать с одним correctness axis без qualified route/manual protocol. Review ingest возможен без обязательного integrity receipt; безопасность review04 обеспечил оркестратор, а не этот API.

**Affected code/schema.** `validate_review_return_semantics`, `cmd_ingest`, `cmd_prepare_review`, `cmd_integrate`, `check_integrity`, `review policy schema`.

**Минимальное безопасное и системное исправление.**

1. Integrate должен принимать review/round refs и неизменяемые content hashes, а не альтернативные return bytes. Любой conflicting duplicate во всех entry points отвергать одинаково.

2. Единая semantic predicate: PASS только при fulfilled required criteria, допустимых выполненных independent checks, отсутствии blocking findings и удовлетворённой policy всех required axes. Невыполненный optional check требует явной typed policy, а не произвольного PASS.

3. Ввести review round/obligations и обязательный per-ticket risk policy. Pending/failed/stale/contaminated required axis блокирует integrate; disagreement закрывается evidence-based adjudication, не выбором удобного PASS.

4. Проверять current candidate generation, intent/publication и integrity receipt до ingest; hash актуального ledger/baseline, immutable export и stop evidence обязательны для authoritative verdict.

5. Не закрывать все review issues ticket одним успешно исправленным finding; пользоваться projection AH-01.

6. Интеграция не снимает external blocker и не делает CONTINUATION обычным candidate. Финальный predicate должен проверять current candidate quality и актуальные debts независимо от того, какой worker его произвёл.

**Regression.** Q01, Q02, Q04, Q14, Q16, Q18, Q19, Q24, Q29, Q31, Q32, Q33.

**Backward compatibility.** Старые PASS records без required proofs нельзя ретроактивно считать qualified. Нужны fresh review либо явно классифицированное historical/unqualified evidence; original return не переписывается.

**Existing-run recovery.** T02 risk=critical. Review05 можно использовать как accepted implementation evidence для repair, но сам по себе он не заменяет missing critical transport/axis qualification перед будущей интеграцией.

**Граница runtime.** Внутри skill; внешний runtime нужен только для предоставления фактических stop/isolation observations.

### AH-05 — P0 — Effect journal не замкнут и general candidate слабее continuation candidate

**Root cause.** Состояние side effect и доменная публикация candidate независимы, completion не общее. Reconcile принимает только prepared; uncertain и abandoned не имеют пригодных повторных переходов. General candidate доверяет минимальному PASS receipt, в отличие от строго проверяемого continuation.

**Evidence.**

`source/tools/ledger.py:2209–2260; 2354–2573; 2574–2654` — Reconcile applied не связывает candidate; candidate требует prepared; uncertain resolve недоступен; abandoned prepare возвращает success без смены состояния.

`source/design/02-run-ledger-and-artifacts.md:section Side effects and crash reconciliation` — Документированный recovery commit-without-receipt расходится с композицией команд.

`P02_uncertain_dead_end`

`P03_reconciled_candidate_dead_end`

`P14_unaudited_fake_candidate`

`P26_abandoned_effect_retry`

**Failure modes.** Commit существует, reconcile-effect applied принят, candidate отвергает applied operation; attempt без candidate. uncertain требует reconcile_uncertain_effect, которого нет. unchanged→abandoned советует same operation ID; повтор prepare не rearm-ит этот ID. Candidate с несуществующим SHA и чужим operation target/base/authority публикуется при минимальном JSON PASS receipt.

**Affected code/schema.** `cmd_prepare_effect`, `cmd_reconcile_effect`, `cmd_candidate`, `cmd_preserve_blocked_candidate`, `operation schema`, `publish`.

**Минимальное безопасное и системное исправление.**

1. Ввести typed operation state machine prepared→applied/uncertain/abandoned и audited resolution uncertain→applied/abandoned. Retry прежнего logical operation оформлять явно, не маскировать abandoned как prepared.

2. Сделать finalize-effect единым для обычного candidate, continuation и recovery: проверить receipt и atomically опубликовать operation completion + candidate linkage + next_action. Existing applied effect с неполной domain projection восстанавливать без повторного commit.

3. General candidate должен переиспользовать строгие Git/base/tree/parent/target/authority/write-set/cleanliness проверки continuation. Receipt и его независимый audit сохранять content-addressed, не external:ID без bytes.

4. Перед эффектом фиксировать exact expected_before, intended tree, checkout/common-dir, operation identity, authorization и policy. При legacy missing intent не придумывать доказательство: fresh audit+explicit adjudication либо BLOCKED.

5. Fault-inject каждый durable boundary: before/after prepare, actual commit, receipt, object publication, ledger replace, snapshot; новая попытка не повторяет уже выполненный effect.

**Regression.** Q01, Q06, Q18, Q22, Q23, Q24, Q34.

**Backward compatibility.** Старые operations без intended tree или immutable receipt могут остаться unverifiable. Нужна отдельная migration classification и receipt-bound reconciliation; нельзя автоматически делать applied по одному HEAD.

**Existing-run recovery.** У Worker05 op уже applied и continuation linkage присутствует; это не повод повторять commit. До нового worker проверить отсутствие иных prepared/uncertain ops. Нужны repairs framework, а не новый product commit сейчас.

**Граница runtime.** Внутри skill; внешний runtime нужен только для предоставления фактических stop/isolation observations.

### AH-06 — P0 — Нет единого phase/control/terminal/owner precondition для mutators

**Root cause.** Transaction обеспечивает token/revision CAS, но не общую допустимость transition. Guards локальны; часть команд mutates terminal/QUIESCING/RECOVERING state. next_action — вручную записываемый текст, не следствие фактов. Epoch не представляет фактическую остановку writer.

**Evidence.**

`source/tools/ledger.py:624–650; 1953–2045; 2072–2175; 4808–5037` — Dispatch не запрещён после cancel request; recover не запрещён после CANCELLED; amend пишет ACTIVE при quarantined attempts.

`source/tools/ledger.py:4969–5003` — Cancel finalize читает stop evidence, но не сохраняет его immutable reference в transition.

`P04_dispatch_while_quiescing`

`P05_terminal_recover`

`P19_review_epoch_registration`

`P31_manual_interrupted_import`

**Failure modes.** QUIESCING run принимает новый worker. Terminal CANCELLED run reopens through recover. Legacy/terminal transitions могут сменить control не закрыв blockers/leases; import-manual принимает INTERRUPTED attempt. Generic gate может выражать action, для которого не существует штатной команды. При takeover returned worker с active reservation не проходит ту же quarantine/reuse процедуру, что PREPARED.

**Affected code/schema.** `transaction`, `cmd_dispatch`, `cmd_authorize_repair`, `cmd_gate`, `cmd_amend`, `cmd_cancel`, `cmd_recover`, `cmd_import_manual`, `validate_ledger`.

**Минимальное безопасное и системное исправление.**

1. Ввести centralized transition table с pre/post invariants для каждого mutator, включая phase, control, epoch, subject, terminal immutability, expected revision и effects. Exceptions только именованные и доказуемые, например authorized repair while external blocker retained.

2. В QUIESCING/PAUSED/RECOVERING запретить new dispatch до proof-carrying resume. CANCELLED/FAILED/ACCEPTED не открываются recover; successor — новая namespace.

3. Сделать next_action/allowed_commands derivation из active facts; каждый emitted action обязан иметь handler или explicit external/owner decision с точным условием снятия.

4. Cancel/takeover/lease release должны сохранять validated stop/reconciliation evidence refs; static bool receipt не заменяет runtime proof, но сама evidence не должна теряться.

5. Amendment quiesces affected writers и не возвращает ACTIVE до доказательства stop/reuse; ownership invalidation не означает исчезновение процессов.

6. Разделить replay исторической операции и новый переход. Same-byte idempotent response не выдаёт разрешения повторно spawn-ить старую попытку.

**Regression.** Q14, Q15, Q16, Q20, Q21, Q22, Q23, Q26, Q35, Q36, Q37.

**Backward compatibility.** Central guards обнаружат ранее допустимые составные состояния. В read-only diagnostics выводить причину и migration path; не переписывать автоматически terminal control или releases.

**Existing-run recovery.** Перед migration ревизии58 остановка/проверка writers и snapshot. Не использовать текущий recover как универсальный reset; original frozen run остаётся BLOCKED до доказанного targeted recovery.

**Граница runtime.** Внутри skill; внешний runtime нужен только для предоставления фактических stop/isolation observations.

### AH-07 — P0 — Immutable evidence/canonical publication не защищены единообразно

**Root cause.** cmd_amend пишет canonical path до owner/revision/duplicate checks и допускает overwrite. Content-addressed reads stored_payload не сверяют bytes с hash из имени. Atomic ledger replace не обеспечивает атомарность всего набора canonical side effects.

**Evidence.**

`source/tools/ledger.py:895–903; 4808–4870; 610–622` — Unverified object reads и pre-fence canonical write. Snapshot/write ordering требует replay после commit.

`P23_hash_addressed_read`

`P27_failed_amend_mutates_document`

**Failure modes.** Отклонённый stale-owner amend изменяет canonical document при неизменном ledger revision. Изменённый object под прежним SHA name используется provenance reader без hash error. Crash/failure после canonical write до ledger commit оставляет не orphan, а повреждение ранее referenced immutable bytes.

**Affected code/schema.** `cmd_amend`, `stored_payload`, `object_store`, `atomic_write`, `publish`, `canonical_document_path`, `verify_manual_inventory`.

**Минимальное безопасное и системное исправление.**

1. Все authority/CAS/existence checks делать под lock до canonical publication; existing canonical path допускает только identical bytes и не переписывается. Unique staged objects публиковать без overwrite, после полного validation.

2. Добавить verified_object_read: namespace+regular non-symlink+hash name+content hash+schema. Использовать для packets/returns/receipts/auth/provenance; design-only hash validation недостаточно.

3. Нормализовать transactional write plan: side effects могут оставлять только безопасные unreferenced immutable objects, никогда изменить уже referenced document при ошибке.

4. Сделать reconcile после ledger-replace/snapshot failure распознаваемым по operation/event ID; не интерпретировать диагностическую ошибку post-publication как отсутствие commit.

5. Проверять complete manual export inventory, а не произвольное непустое подмножество receipt hashes (совместно AH-09).

**Regression.** Q22, Q23, Q34, Q35, Q38.

**Backward compatibility.** Проверка hash всех referenced объектов может обнаружить старую corruption. Никакого silent rewriting hash; restore only independently verified source bytes либо explicit unavailable evidence.

**Existing-run recovery.** Проверить hashes frozen packet, live objects и canonical docs до binding migration. В evidence нет полного installed runtime и live canonical files, поэтому их current integrity нельзя объявить проверенной этим audit.

**Граница runtime.** Core fixes полностью внутри skill. Файловая атомарность и процессные блокировки должны быть квалифицированы на используемом runtime/filesystem.

### AH-08 — P0 — Legacy admitted state сохраняет self-produced input contracts после исправления публикации

**Root cause.** Новый design_bundle имеет early input/output guard, но общий validator, ready-ticket и dispatch не применяют тот же invariant к уже существующему run. Schema version 1.0 не выражает семантический разрыв старых и новых bindings.

**Evidence.**

`source/tools/ledger.py:790–903; 346–524; 2046–2071` — Specialized binding validator не часть общего consistency validator.

`source/SKILL.md:22–42` — ticket.contract_refs объявлены executable inputs, producer_refs — outputs; self-input запрещён.

`evidence/state/successor/rev-058-ledger.json :: /design_publication/ticket_refs; /tickets; /contracts` — 9 текущих tickets пересекают input contract_refs и собственные producer_refs; все эти contracts active. validate_ledger(verify_files=False) PASS, specialized binding validation FAIL.

**Failure modes.** Release исправляет new publication, но admitted legacy state остаётся несовместимым с новым guard. Повтор affected G2/G3/republish после repair способен обнаружить ранее скрытый self-input; successor сам по себе не очищает модель bindings. Нельзя понять по active flag, доказана ли доступность contract deliverable/переданных resources.

**Affected code/schema.** `validate_design_bundle`, `validate_ticket_contract_bindings`, `validate_current_design_contract_bindings`, `validate_ledger`, `cmd_ready_ticket`, `cmd_dispatch`, `schema version/migrations`.

**Минимальное безопасное и системное исправление.**

1. Сформировать authoritative contract model: input specification/version отдельно от produced implementation/deliverable proof. Если ticket читает ранее опубликованный interface и производит его реализацию, это две разные связи, не self-dependency одного readiness объекта.

2. Вынести binding invariant в общий validator и admission preflight для всех текущих tickets, а не только новых bundles.

3. Сделать owner-approved, hash-addressed legacy binding migration с original+replacement refs и scope-effect classification. Ни молча удалять refs, ни превращать proposed в active.

4. No-scope-change correction должна иметь явный validated equivalence contract; material contract/intent change требует нового publication и affected G2/G3. Отсутствие такого migration path в v1.0.11 — отдельный release blocker.

5. Определить typed proof активации output contract и readiness consumers, включая наследуемые predecessor artifacts.

**Regression.** Q11, Q20, Q21, Q27, Q35, Q39.

**Backward compatibility.** Главный migration риск: новый strict validator немедленно отвергает реальные current tickets. Поэтому нужен диагностический read path и dry-run migration прежде первого live write новой версией.

**Existing-run recovery.** Rev58: T02 ARCHITECTURE; T03 RUNTIME+ARCHITECTURE; T04 SEMANTIC+QUICK; T05 EVIDENCE+SECURITY; T06 ASSESSMENT+ARCHITECTURE; T07 API-UI; T08 SECURITY; T10 MIGRATION; T11 ARCHITECTURE. Реальное значение связей надо подтвердить документами/owner decision, недостающие live design bytes в пакете не заменять предположением.

**Граница runtime.** Полностью внутри skill/schema; решение о смысле contract и допустимом scope принадлежит owner.

### AH-09 — P0 — Manual critical/G5 transport не замкнут в общий review→repair lifecycle

**Root cause.** prepare-handoff принимает review или acceptance packet и меняет существующий attempt; import-manual валидирует только acceptance packet, не выполняет обычный review ingestion/resolution и безусловно трактует PASS как переход к ACCEPT. Нет разделения per-ticket critical axis и final G5.

**Evidence.**

`source/tools/ledger.py:1550–1565; 3741–4013` — Manual BLOCK не materializes findings; PASS check outcomes не проверены, inventory лишь subset; нет guard INTERRUPTED; per-ticket PASS не releases worker reservation.

`source/phases/accept.md:13–39` — Требуются critical axes, repair wave при BLOCK и fresh G5; native behavior не должен обходить manual protocol.

`P29_manual_BLOCK_findings`

`P30_manual_failed_PASS`

`P31_manual_interrupted_import`

`P32_manual_packet_mismatch`

**Failure modes.** Manual BLOCK принят, но durable findings/issues отсутствуют, next_action всё ещё import_manual_review; authorize-repair нечем обосновать. Manual PASS с failed check и inventory без candidate-export принимается. Per-ticket manual PASS помечает ticket INTEGRATED и phase ACCEPT, оставляя worker lease active. Interrupted reviewer return становится authoritative через import-manual. Review-kind handoff регистрируется, но следующий import отвергает его как не acceptance.

**Affected code/schema.** `cmd_prepare_handoff`, `cmd_import_manual`, `validate_acceptance_return_semantics`, `verify_manual_inventory`, `acceptance/review round schemas`.

**Минимальное безопасное и системное исправление.**

1. Разделить review purpose: ticket_change, critical_axis, final_g5; transport независим от purpose. Тип packet/return должен быть согласован при prepare и import.

2. Импортировать любой authoritative review через единый identity/currentness/integrity/semantic admission AH-04; BLOCK materializes individually repairable findings и obligations, next_action переходит к triage, не wait.

3. Critical-axis PASS закрывает axis obligation текущего ticket, не переносит run сразу в ACCEPT. Ticket integration отдельно закрывает required reviews и reservation. Только final G5 PASS разрешает G6 candidate.

4. Проверять complete export manifest/inventory, packet/projection hashes, explicit stop receipt, epoch/current state, candidate generation. Interrupted/old-epoch payload остаётся historical либо получает специальную current-owner revalidation, не silent import.

5. New handoff — новый immutable attempt/packet registration; не переписывать accepted packet/return/attempt role ради повторного транспорта.

6. G5 findings группировать в dependency-ordered repair wave с per-finding re-review и одним fresh full G5 после общего candidate.

**Regression.** Q04, Q16, Q19, Q22, Q23, Q31, Q33, Q36, Q38, Q40.

**Backward compatibility.** Старые manual acceptance records lacking outcome refs/current candidate binding нельзя повышать до новой qualification автоматически. Они остаются historical with evidence grade.

**Existing-run recovery.** T02 critical: сначала исправить механизм, затем нужные fresh axis reviews на конечном repaired candidate. Review05 implementation findings сохраняются, но manual G5 scope нельзя подменить только этим review.

**Граница runtime.** Admission/projection fixes внутри skill. Реальная чистота session, доступные connectors и границы sandbox подтверждаются только scoped runtime/operator receipts; абсолютной изоляции helper не доказывает.

### AH-10 — P1 — Successor, predecessor evidence и wave boundary не имеют единого executable closure

**Root cause.** В предоставленном helper нет отдельного successor/wave transition и структуры wave/parent lineage с proofs. Init создаёт новую namespace; перенос scope/contracts/resources остаётся orchestration protocol. Contract active не доказывает комплектность унаследованных artifacts.

**Evidence.**

`source/tools/ledger.py:1666–1705; 4871–5077` — Есть init/gate/cancel/recover, но нет create-successor/wave-finalize/inherit-artifacts API.

`source/design/02-run-ledger-and-artifacts.md:section successor/checkpoint context` — Продолжение должно ссылаться на checkpoint и проверять missing artifacts.

`evidence/state/predecessor/rev-122-cancel-terminal.json :: /lifecycle` — Предшественник CANCELLED.

`evidence/state/successor/rev-058-ledger.json :: /contracts; /lifecycle` — Есть inherited producer PREDECESSOR-T01-R14; внешний evaluation-resource blocker остаётся активным.

**Failure modes.** Новый run может повторить старые семантические bindings либо не иметь файлов, на которые ссылается унаследованный contract. Wave завершена по тексту next_action, но не по aggregate findings/leases/effects/integration closure. User checkpoint и successor authority references нельзя проверить как единую цепь exact subject/scope.

**Affected code/schema.** `cmd_init`, `cmd_cancel`, `cmd_gate`, `successor manifest schema`, `contract readiness`.

**Минимальное безопасное и системное исправление.**

1. Добавить небольшой typed successor manifest: predecessor run/revision/hash, candidate/tree, accepted scope decision, inherited artifact digests, explicit exclusions/unknowns. Predecessor terminal history не изменять.

2. Перед activating inherited contracts проверять реальную доступность authorized resources и соответствие criteria/artifact hashes. Missing resources = explicit BLOCKED, не fabricated active.

3. Wave boundary определить как aggregate predicate по перечисленным tickets, review obligations, current candidate, leases/effects и next eligible work; не создавать новый scheduler rewrite.

4. Разрешить user checkpoints только из persisted policy/authority-sensitive decisions; semi и full не обходят critical/oracle/cost/irreversible authority.

5. Qualification на predecessor CANCELLED→successor: старый ledger byte-identical, новый owner/scope/namespace, no shared-writer lease theft.

**Regression.** Q20, Q21, Q35, Q37, Q39, Q40.

**Backward compatibility.** Исторические successor runs без explicit parent manifest могут быть classified legacy; связь восстанавливается только по устойчивым hashes/refs, неоднозначное inheritance не активируется.

**Existing-run recovery.** Не создавать ещё один successor автоматически ради rev58 binding bug. Сначала targeted state migration; если потребуется material scope change — отдельное owner решение и проверка наследования.

**Граница runtime.** В основном skill. Фактические файлы/dependencies и допустимая isolated copy требуют filesystem/runtime observations.

### AH-11 — P1 — Регистрация попытки не фиксирует наблюдаемый native spawn/wait/stop как durable protocol

**Root cause.** Helper сознательно не запускает модели. При этом dispatch оставляет PREPARED, schema допускает DISPATCHED, но отдельного перехода с наблюдаемым native handle нет; timeout/stop между регистрацией и возвращением в основном остаётся инструкцией оркестратору.

**Evidence.**

`source/tools/ledger.py:1953–2045; 2176–2208; 5004–5037` — Registration/termination есть, spawn/handle observation transition отсутствует; same-byte dispatch replay сохраняет prepared success.

`source/SKILL.md:18; 70–80` — Helper bookkeeping-only; bounded waits и reconciliation обязательны для orchestrator.

`source/design/02-run-ledger-and-artifacts.md:section Takeover, checkout reuse and recovery` — Epoch не убивает внешние writers; нужны stop/reuse proofs.

**Failure modes.** Crash после native spawn до handle persistence оставляет неизвестную liveness. Повтор dispatch response можно ошибочно трактовать как разрешение снова spawn. Timeout/потеря UI handle не доказывает stop; safe lease reuse не выводится только из ledger. Return malformed не может превращаться в user routine checkpoint без конкретного authority cause.

**Affected code/schema.** `cmd_dispatch`, `cmd_terminate_attempt`, `cmd_recover`, `attempt schema`, `orchestrator runtime adapter/instructions`.

**Минимальное безопасное и системное исправление.**

1. Сохранить bookkeeping-only helper, но добавить durable observations: spawn-request identity, observed handle/session when available, observed start/progress/stop, inbox fingerprint, runtime build and coverage limits.

2. Replay dispatch возвращает exact existing disposition и запрет повторного spawn; unknown actual spawn не retry-ится автоматически.

3. Связать lost/interrupted/reuse с AH-03 proof-carrying finalization; missing runtime observation → explicit quarantine с выполнимым условием снятия.

4. Провести runtime qualification: worker/reviewer interruption, descendant tools, wait liveness, malformed inbox, crash before/after spawn. Не объявлять unit-test mocks доказательством поведения Codex.

**Regression.** Q14, Q15, Q16, Q22, Q23, Q26, Q36, Q37.

**Backward compatibility.** Legacy attempt без handle остаётся unknown, не not-started. Migration не выдумывает start/stop timestamps или native capabilities.

**Existing-run recovery.** Для Worker05 в пакете есть accepted return/continuation proof, но live absence of background writers всё равно надо подтвердить на реальной машине перед reuse. Это не выполнено данным audit.

**Граница runtime.** Смешанная: durable adapter/contracts внутри skill; создание/остановка native процессов, скрытая память, лимиты и runtime wait вне полного контроля skill.

### AH-12 — P1 — Qualification не доказывает closure текущей state machine и пакет неполон для воспроизведения release claims

**Root cause.** Model tests проверяют достижимость ручного JSON-графа, не реализации CLI и guards. Много tests начинают с вручную seed-нутого legal state и заканчивают до следующего проблемного transition. Часть release qualification и fixtures отсутствует в приложенном source packet.

**Evidence.**

`source/tests/test_state_machine_model.py:1–67` — Reachability analysis по lifecycle-model.json без вызовов ledger transitions.

`source/tests/test_continuation_candidates.py:154–238` — Positive continuation scenario доходит до repair dispatch, не возвращает repair и не интегрирует.

`baseline-tests.log`: unittest discover: 80 entries, 71 pass, 2 failures+6 errors from unavailable packet dependencies, 1 opt-in skip.

**Failure modes.** Green helper/regression tests не предотвращают цепочку соседних lifecycle holes. Нельзя независимо подтвердить заявленную полную qualification и runtime/source parity по неполному packet. Schema 1.0 принимает несовместимые semantic states без schema-versioned migration contract.

**Affected code/schema.** `tests/*`, `experiments/v104_lifecycle_qualification.py (отсутствует в packet)`, `experiments/v1_40_ticket_qualification.py (отсутствует в packet)`, `schemas/contracts.schema.json`, `release/install manifest`.

**Минимальное безопасное и системное исправление.**

1. Сделать runnable full-source test package с fixtures и pinned hashes; missing package dependencies отделить от assertion failure кода.

2. Превратить matrix Q01–Q40 в CLI end-to-end suite с реальным disposable Git, проверкой state tuple после каждого шага и исполнением advertised next command. Legacy corrupt fixtures разрешены только отдельным migration tests.

3. Привязать transition table/reducer к generated tests и assertions; проверять достижимость safe recovery для любого accepted nonterminal post-state при явно смоделированных external blockers.

4. Добавить crash/fault injection до/после каждого durable write и same-byte/conflicting replay каждого mutator.

5. Ввести semantic schema version, legacy read-only diagnostics, explicit migration registry/provenance/rollback-to-snapshot plan и dry-run на supplied frozen revisions.

6. Run complete CI + runtime qualification и install/source parity до общей v1.1.0 release; не считать тестовый JSON-граф доказательством implementation closure.

**Regression.** Q01–Q40, P01–P32 as negative/positive regression seeds.

**Backward compatibility.** Новая schema может заблокировать legacy runs; сначала read-only classify, затем owner-approved append-only migration. Нельзя silently auto-upgrade неизвестные states.

**Existing-run recovery.** Использовать rev58 и retained predecessor/successor snapshots как immutable regression fixtures; original archives не модифицировать и не fabricating missing rev32/37/47/52.

**Граница runtime.** Полная CLI qualification внутри repo при комплектных fixtures; реальный Codex qualification отдельно, не заменяется Python.

### AH-13 — P2 — Операционные метрики и представления не отделяют регистрацию от фактического исполнения

**Root cause.** Счётчики и presentation слои ориентированы на model/helper intent: dispatch увеличивает spawn_calls при регистрации, хотя native spawn вне helper. Проектный target малого числа helper calls не является фактическим протоколом v1.0.11.

**Evidence.**

`source/tools/ledger.py:1953–2045; 1726–1791` — Учёт регистрации, usage и views не является runtime observation.

`source/design/02-run-ledger-and-artifacts.md:section Atomic publication and intent-level API` — ≤4 calls — design/economic target, не frozen CLI guarantee.

**Failure modes.** На дашборде registration count может выглядеть как фактические native spawns. Большой history может затруднять чтение active blockers и recovery obligations, даже после исправления underlying model.

**Affected code/schema.** `usage accounting`, `cmd_status`, `cmd_render_view`, `dashboard projection`.

**Минимальное безопасное и системное исправление.**

1. Разделить prepared_attempts, observed_spawns, observed_stops и unknown_spawn; показывать источник метрики.

2. После P0 correctness отобразить current candidate quality, active findings/debts, historical count и exact executable next action в status/dashboard.

3. Оптимизацию числа calls и индексацию history делать после qualification; не сокращать проверки ради экономии токенов.

**Regression.** Q14, Q21, Q23, Q37.

**Backward compatibility.** Старые spawn_calls не переинтерпретировать как observed runtime events; обозначить legacy estimate.

**Existing-run recovery.** Для rev58 достаточно читать raw ledger+derived audit projection; реорганизация UI не prerequisite recovery.

**Граница runtime.** Внутри presentation/accounting; наблюдаемые runtime metrics доступны только при поддержке адаптера.

### 4.1. Полный реестр независимых диагностических трасс

| Probe | Наблюдение | Related root |
| --- | --- | --- |
| P01_missing_ticket_binding | Global-only affected_refs приняты; repair отвергается как not bound; await остаётся. | AH-01 |
| P02_uncertain_dead_end | uncertain operation нельзя снова reconcile. | AH-05 |
| P03_reconciled_candidate_dead_end | Реальный commit + reconciled applied operation не позволяют опубликовать candidate. | AH-05 |
| P04_dispatch_while_quiescing | Dispatch после cancel request создаёт RUNNING ticket в QUIESCING run. | AH-06 |
| P05_terminal_recover | recover открывает CANCELLED run как RECOVERING. | AH-06 |
| P06_conflicting_review_integrate | integrate принимает conflicting PASS после accepted BLOCK и оставляет review_result=BLOCK. | AH-04 |
| P07_failed_check_PASS | Review PASS с failed check интегрируется. | AH-04 |
| P08_critical_policy_bypass | Critical ticket интегрируется с одним correctness axis без qualified policy. | AH-04 |
| P09_allow_deny_overlap | Allow/deny overlap принимается в active lease. | AH-02 |
| P10_worker_wrong_ticket | Worker return с чужим ticket_id ingested. | AH-02 |
| P11_stale_modify_base | Modify repair принимает несуществующий source/base. | AH-02 |
| P12_undispatchable_unchanged_auth | Authorize принимает unchanged repair, следующий dispatch отвергает. | AH-02 |
| P13_lost_partial_create | LOST create с partial file не продолжить обычным modify repair. | AH-03 |
| P14_unaudited_fake_candidate | General candidate принимает fake SHA/minimal receipt без реального Git commit. | AH-05 |
| P15_empty_HANDOFF_closure | Initial empty HANDOFF не закрывается close-blocked-attempt. | AH-03 |
| P16_parallel_review_BLOCK_bypass | Один PASS интегрируется при другом current BLOCK. | AH-04 |
| P17_review_ingest_without_barrier | Authoritative review ingest не требует integrity receipt. | AH-04 |
| P18_initial_nochange_BLOCK | Initial empty BLOCK не закрывается close-blocked-attempt. | AH-03 |
| P19_review_epoch_registration | Prepare-review сохраняет epoch=0 при packet epoch=99. | AH-02, AH-06 |
| P20_duplicate_happy_control | Положительный контроль: exact duplicate dispatch и worker ingest не меняют revision. | Positive control |
| P21_continuation_nochange | No-change repair после continuation не закрывается: previous return обязан быть DONE. | AH-03 |
| P22_review_source_preserve | Source review допустим для dispatch, но отвергается при subsequent preserve. | AH-02, AH-03 |
| P23_hash_addressed_read | stored_payload читает tampered bytes под неизменным SHA filename. | AH-07 |
| P24_historical_finding_reuse | Finding старого candidate снова авторизует modify repair текущего candidate. | AH-01, AH-02 |
| P25_duplicate_prepare_review | Same-byte prepare-review retry не idempotent. | AH-06, AH-12 |
| P26_abandoned_effect_retry | prepare-effect возвращает prepared success для op, всё ещё abandoned. | AH-05 |
| P27_failed_amend_mutates_document | Отклонённый stale-owner amend перезаписывает canonical document до fence. | AH-07 |
| P28_adjudication_blocker_projection | PASS adjudication оставляет disagreement issue blocking без invalidation. | AH-01 |
| P29_manual_BLOCK_findings | Manual BLOCK принят без durable findings/issues, action всё ещё import_manual_review. | AH-09 |
| P30_manual_failed_PASS | Manual PASS с failed check и неполным inventory принят; ticket INTEGRATED, worker lease active, phase ACCEPT. | AH-09 |
| P31_manual_interrupted_import | Manual return от INTERRUPTED review принимается как authoritative. | AH-06, AH-09 |
| P32_manual_packet_mismatch | Review-kind handoff подготовлен, но import требует acceptance-kind packet. | AH-09 |

Все 32 финальные пробы завершились заявленным observation и последующей проверкой `validate_ledger` fixture state. Это прямо подтверждает центральный вопрос: **общий validator принимает состояния, нарушающие более сильный контракт следующей команды или протокола**. Оно не означает, что 32 tests квалифицируют Autopilot: диагностический assert здесь ожидает существующий дефект. После исправления соответствующий negative regression должен ожидать rejection-before-publication или успешное безопасное continuation, а не прежнее observation.

Модель угроз этих проб — ошибочный/неполный вызов со стороны кооперативного оркестратора, повтор после сбоя и несовместимые helper contracts. Это не утверждение, что Python защищает систему от злонамеренного owner с прямым доступом к файлам. В частности P14/P23 доказывают пропущенный consistency check, не универсальную security boundary операционной системы.

## 5. Architectural / root-cause analysis

### 5.1. Что именно не замкнуто

[STATIC + EXECUTED] Реальное состояние — не один `ticket.state`, а сочетание:

`S = (phase, control, owner/epoch, ticket, attempt, candidate, leases, review rounds, findings/obligations, authorizations, effects, next_action)`.

`validate_ledger` в основном проверяет форму, ссылки, отдельные ограничения и часть физических hashes. Он не проверяет, что это сочетание соответствует одной допустимой строке lifecycle. Поэтому существуют два независимых класса дефектов: **ложноположительное разрешение** опасного перехода и **ложноположительное принятие** состояния, которое потом оказывается необрабатываемым. P06/P16 показывают первый класс; P01/P03/P12/P21 — второй. Эти классы надо тестировать раздельно: запретить лишнее недостаточно, если единственный безопасный выход тоже запрещён.

[PROPOSED] Контракт любой команды должен включать четыре свойства:

1. Все детерминированные условия следующего заявленного шага проверяются до публикации состояния, обещающего готовность к этому шагу. Изменение внешнего мира между командами допустимо; заведомо недиспетчеризуемая authorization — нет.
2. Успешный переход сохраняет не только schema validity, но и cross-entity invariants: одно значение current candidate, согласованные subject/epoch/base, отсутствие несовместимых writers и непротиворечивая blocker projection.
3. `next_action` либо исполним текущей штатной командой, либо описывает конкретное внешнее условие/owner decision и существующий переход после получения evidence. Строка «reconcile actual state» без подходящего handler для данного класса повреждения — не завершённый recovery contract.
4. Любой nonterminal state имеет безопасный дальнейший маршрут: продолжение, ожидание известного внешнего условия, доказательное reconciliation либо остановка/cancel без потери history. Это **не** требование автоматически завершать задачу вопреки неизвестному writer или неразрешённому blocker.

Устойчивость к сбою означает повторяемое распознавание уже случившегося эффекта, а не обещание одной атомарной транзакции между Git, filesystem, JSON ledger и внешним Codex runtime. Именно для этой границы нужен доказательный effect protocol.

### 5.2. Ответы на вопросы о модели данных

| Вопрос | Вывод по v1.0.11 | Ограниченное структурное изменение |
| --- | --- | --- |
| Перегружен ли current_attempt? | Да: latest worker, current writer и holder candidate совмещены. close-blocked вынужден возвращать указатель назад. | Разделить current_worker_attempt / last_worker_attempt и current_candidate. History linkage не меняется при освобождении writer. |
| Перегружен ли next_action? | Да: human instruction, scheduling decision, recovery advice и durable progress marker. Он не выводится единообразно из фактов. | Derived action из central projection + именованные external decisions. Кэш допустим только с revision/projection hash и проверкой соответствия. |
| Достаточен ли один ticket status? | Нет как единственный источник истины: BLOCKED может иметь candidate, writer reservation, accepted review и разрешённый ограниченный repair одновременно. | Оставить компактный display status, а readiness вычислять по orthogonal attempt/candidate/obligation state; не плодить десятки status без инвариантов. |
| Нужен ли явный current_candidate? | Да. Сейчас он косвенно получается из current_attempt и receipt, что ломает no-change/interrupt/continuation. | Candidate ID с producer attempt, SHA/tree/base, generation/parent, quality DONE/CONTINUATION, blocker obligations и интеграционным статусом. |
| Historical/active findings разделены? | Недостаточно. invalidated_by, issue impact, lifecycle.issue_refs и singular repair_contract_ref не образуют согласованного lifecycle. | Raw findings immutable; current applicability, verification debt, supersession и resolution — отдельные auditable facts/projection. |
| Input/output contract bindings смешаны? | Да в frozen текущем состоянии; новый publisher это запрещает, старые tickets продолжают жить. | Input specification/version и produced deliverable/evidence моделировать разными отношениями; owner-approved migration семантики legacy binding. |
| Validation дублируется? | Да. Shared helpers существуют, но guards вызываются не на всех путях и с разными ранними выходами. | Canonical admission objects для AttemptPlan, ReviewPlan, CandidateProof, RepairAuthorization; один validator каждого контракта для всех callers. |
| Recovery стал ad hoc? | Да по покрытию: сильные локальные proof routines обслуживают узкие комбинации DONE/create/previous DONE. | Общая таблица attempt finalization + typed reuse proofs; старые строгие validators переиспользовать как частные proof providers. |
| Нужна ли migration/schema version? | Да: version 1.0 не позволяет отличить несовместимые semantic states. | Версия state contract + migration registry, read-only diagnostics, append-only migration receipts и dry-run retained revisions. |

### 5.3. Предлагаемый minimum structural refactor

[PROPOSED] Не нужно переписывать весь skill или переводить весь ledger в event-sourced систему. Достаточно сделать небольшой authoritative слой вокруг существующих сущностей:

**Transition registry / reducer.** Каждая mutating CLI-команда объявляет допустимые phase/control, expected subject/currentness, обязательные proofs, write plan и postconditions. Чистая часть `transition(state, command, verified_facts)` возвращает новый state и side-effect plan; исполнение выполняется под существующим owner/revision fence. Git/runtime observations поступают как evidence, а не вызываются внутри «чистого» reducer. Нельзя делать этот слой только ещё одной документацией: те же predicates должны использовать CLI и qualification tests.

**Единый admission.** `authorize-repair` и `dispatch` получают один candidate-bound AttemptPlan. В authorize проверяется возможность всего согласованного плана, а не только существование finding. Если точная packet zone ещё неизвестна, нельзя утверждать полную READY: сначала подготовка плана, затем authorization. Return проверяется против той же registered identity. `prepare-review`, обычный ingest, manual import и integrate используют один ReviewPlan с purpose, transport, required axes, current subject и admissible proof grade.

**Единая derived projection.** `current_candidate`, current review round, active findings, unresolved carry-forward concerns, blocker issues, available authorization и executable action вычисляются совместно. Raw return не правится. Наличие нового candidate не закрывает старую проблему автоматически, но старый subject также не должен оставаться ложной командой «ремонтировать предыдущий candidate».

**Total attempt finalization.** Для DONE / BLOCKED / HANDOFF / FAILED / LOST / INTERRUPTED / quarantined задаётся disposition отдельно от факта return: no changes; reusable owned changes; foreign/unknown changes; unknown writer. Допустимые результаты — ordinary candidate, continuation, восстановление предыдущего candidate, released reservation или карантин с точным proof requirement. Нельзя превращать BLOCK в DONE, чтобы воспользоваться единственной удобной веткой.

**Общее completion внешних эффектов.** Effect остаётся идентифицируемым от prepare до применения и привязки к ledger. Физический commit, проверенный receipt и candidate linkage должны завершаться одним resumable protocol. Applied-but-unlinked — явное промежуточное состояние с finalize handler, а не тупик. Unknown observation остаётся uncertain, но может принять новое доказательство. Replaying старого prepare не возвращает ложное «prepared», если операция уже abandoned.

**Локальные append-only recovery events.** Для binding corrections, supersession, issue adjudication, authorization cancellation и legacy migrations достаточно отдельных immutable записей с exact old/new refs и owner authority. Это сохраняет auditability без полного переписывания формата всех прошлых событий.

Сильные существующие части следует сохранить: recursive path provenance, strict owned-write audit, проверку continuation base/tree/parent, реальные quarantine barriers, design publication currentness и intent-level acceptance binding. Их надо распространить на соседние пути, а не упростить до самого слабого `candidate`/`integrate` contract.

## 6. P0 / P1 / P2 hardening plan

Приоритет здесь соответствует определению владельца: **P0 — до возобновления T02; P1 — до T03; P2 — можно отложить**. Это не CVSS и не заявление, что каждая найденная ветка уже эксплуатировалась в production. Например, manual-path дефекты относятся к P0 потому, что текущий T02 имеет `risk=critical` и его ближайший корректный lifecycle не должен обходить этот barrier.

Детальные root cause, evidence, functions, fixes, regressions, migration risk и runtime dependency каждого пункта находятся в разделе 4 и JSON. Ниже — порядок одного согласованного hardening-pass, а не план выпуска отдельных patch-релизов на каждый symptom.

| Этап работы | Findings / gate | Содержание | Проверяемый результат |
| --- | --- | --- | --- |
| 1. Защитить authority и immutable evidence | P0 AH-07 + базовые AH-06 | Fence до canonical writes; hash-verified readers; terminal/quiescing guards; write-plan/replay contract. | Rejected command не меняет ledger или referenced bytes; cancellation не допускает новый dispatch; terminal не открывается. |
| 2. Зафиксировать semantic state contract | P0 AH-08, AH-01; схема из AH-12 | Candidate identity, subject binding, input/output semantics, active/debt projections, legacy classification. | Rev58 читается диагностически; missing bindings и 9 self-input tickets видны до любого нового worker. Не делается silent normalization. |
| 3. Замкнуть authorize→dispatch→return | P0 AH-02 + AH-06 | Единый AttemptPlan; finding_refs[]; exact source/base/scope/epoch; authorization lifecycle; executable actions. | Любая выданная READY authorization проходит тот же детерминированный preflight, что dispatch; wrong subject/deny/stale lineage отвергаются заранее. |
| 4. Замкнуть attempt/effect/candidate | P0 AH-03 + AH-05 | Total finalization; no-change/partial/continuation/lost; actual candidate proof; resumable applied effects. | Continuation→repair→BLOCK/HANDOFF/DONE и crash windows завершаются без ручных pointer edits и без подмены verdict. |
| 5. Объединить review / manual / integration | P0 AH-04 + AH-09 | Immutable accepted return; check semantics; all required axes; complete inventory; manual BLOCK findings; per-finding closure. | Accepted BLOCK невозможно заменить PASS через integrate; другой required BLOCK удерживает barrier; critical PASS не прыгает в final ACCEPT. |
| 6. Квалифицировать targeted rev58 migration | P0 gate; core tests AH-12 | Frozen fixture→new projection→binding events→group repair preflight; owner decisions для неоднозначных contracts. | Ни один исходный artifact не переписан; next_action соответствует actual next command; external blocker и historical debt сохранены. |
| 7. Квалифицировать whole-run и runtime границы | P1 AH-10, AH-11, AH-12 | Successor/wave/inheritance; spawn/wait/stop observations; полный CLI suite, fault injection, комплектные fixtures, install parity. | Все обязательные lifecycle scenarios проходят; missing fixtures не называются PASS; реальные runtime guarantees и unsupported cases явно разграничены. |
| 8. Улучшить представления | P2 AH-13 | Раздельные registration/runtime metrics, current/history dashboard, оптимизация calls после correctness. | UI отражает authoritative projection; старые counters не выдаются за фактическое число spawns. |

### 6.1. В каком порядке принимать изменения

Работу можно вести на одной release branch по указанным dependency groups. Общая transition specification, базовые invariants и migration contracts должны появиться до фиксов отдельных веток, иначе те снова начнут расходиться. В JSON у каждого finding перечислены зависимости; это порядок инженерной интеграции, не разрешение пропустить остальные обязательные guards.

**До любого live T02 dispatch** необходимы P0 implementation, независимое review этих изменений, обязательные P0 regression/fault-window tests и успешная репетиция recovery на копии frozen state. Нельзя отложить все тесты под предлогом, что AH-12 имеет P1: P1 — полный distribution/whole-run qualification, а проверка исправляемой P0 безопасности входит в сам P0.

Рекомендуемая эксплуатационная граница ещё строже: **выпустить один v1.1.0 после P0 + P1**, а затем возобновить T02. Так текущий проект не становится живым полигоном для недоделанного whole-run hardening. Более раннее P0-only возобновление возможно только как явно ограниченный owner-approved canary с работающими P0 paths; это не общий допуск v1.0.11 и не эквивалент qualified release.

### 6.2. Backward compatibility и migration

Новая версия сначала должна уметь **читать старое состояние без выполнения мутаций**, показать incompatible fields и предложить точный migration plan. Нельзя просто повысить `schema_version`, переписать `affected_refs` на месте или глобально очистить `invalidated_by`/issues.

Предлагаемый protocol: проверить исходный snapshot hash и все доступные referenced bytes; классифицировать неоднозначности; подготовить replacement projection и immutable migration receipt; проверить cross-invariants и запрет несанкционированного расширения scope; опубликовать через owner/CAS. Оригинальные snapshots, returns, receipts, verdicts и candidate hashes остаются историей. Неизвестный source, отсутствующий object или спорный contract не «исправляется по наиболее вероятному смыслу» — такой элемент остаётся явным blocker.

В случае неуспешной миграции до публикации authoritative state не меняется. После успешной публикации откат — не механическое уменьшение revision и не `git reset --hard`: восстановление проверенного snapshot требует отдельного ownership/reconciliation протокола, чтобы не оживить старую authority при уже случившихся внешних эффектах. Repo должен документировать, какие migrations обратимы логически, а какие допускают только forward correction.

## 7. Lifecycle qualification matrix

### 7.1. Статус и обозначения

**Все Q01–Q40 ниже — спроектированные обязательные E2E tests, не утверждение о текущем PASS.** Уже исполненные P01–P32 — диагностические seeds для части этих tests.

`BOOT` означает настоящий CLI-путь на disposable Git: init → intent/requirements → publish design bundle → независимые требуемые G2/G3 → EXECUTE. Основные qualification scenarios нельзя начинать прямым редактированием READY ledger. Исключение — явно обозначенные legacy/malformed/migration fixtures; у них начальный defect является предметом теста и хранится как immutable fixture.

Таблица описывает **целевую hardened модель**. `current_attempt=null` означает отсутствие текущего живого/регистрируемого writer, а `last=A…` сохраняет историческую ссылку; это не инструкция занулить старый v1.0.11 `current_attempt` без миграции. `C… CONTINUATION` — не DONE и не право интеграции. `TARGET:` обозначает новый необходимый transition/handler, не существующую CLI-команду. Имена derived actions также проектные, а не shell commands.

Для промежуточных checkpoint указан допустимый следующий шаг и обязательное завершение сценария. Поэтому сценарий «continuation→repair» не заканчивается успешным dispatch: он должен получить return, пройти review/integrate либо квалифицированный безопасный recovery и только потом считаться выполненным.

### 7.2. Полная матрица checkpoints и обязательного продолжения

#### Q01. Happy path без repair

**Полный путь:** `BOOT→ready→dispatch→DONE→audit→effect→candidate→review PASS→integrate`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | INTEGRATED |
| Run control | ACTIVE |
| Current / last attempt | null; last=A1 RETURNED |
| Current candidate | C1 DONE/INTEGRATED |
| Leases | Все released; no writers |
| Active findings / obligations | ∅ |
| Historical findings | ∅ |
| Authorization state | Нет repair auth |
| next_action | schedule_next_or_g4 |
| Допустимая следующая команда | ready-ticket либо gate G4 |

**Критерий завершения всего сценария:** Продолжить G4→qualified G5 PASS→G6 ACCEPTED; unchanged hashes, zero active leases/effects/blockers.

#### Q02. Один repair

**Полный путь:** `BOOT→C1→review F1→authorize→A2 DONE→C2→targeted+required PASS→integrate`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | INTEGRATED |
| Run control | ACTIVE |
| Current / last attempt | null; last=A2 |
| Current candidate | C2 DONE/INTEGRATED |
| Leases | Все released |
| Active findings / obligations | ∅ |
| Historical findings | F1 resolved с independent proof |
| Authorization state | AUTH1 consumed by A2 |
| next_action | schedule_next_or_g4 |
| Допустимая следующая команда | ready-ticket/gate |

**Критерий завершения всего сценария:** History C1/BLOCK неизменна; exactly one consumed auth and one independently closed F1.

#### Q03. Несколько последовательных repairs

**Полный путь:** `BOOT→C1 F1→A2/C2 F2→A3/C3 F3→A4/C4 PASS→integrate`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | INTEGRATED |
| Run control | ACTIVE |
| Current / last attempt | null; last=A4 |
| Current candidate | C4 DONE/INTEGRATED |
| Leases | Все released |
| Active findings / obligations | ∅ |
| Historical findings | F1…F3 independently resolved/superseded with obligations discharged |
| Authorization state | AUTH1…3 consumed once |
| next_action | schedule_next_or_g4 |
| Допустимая следующая команда | ready-ticket/gate |

**Критерий завершения всего сценария:** Пройти create→modify цепь целиком; никаких ручных pointer edits и stale bindings.

#### Q04. Один repair закрывает несколько findings

**Полный путь:** `BOOT→C1→same-round F1,F2,F3→group AUTH→one A2→C2→per-finding outcomes`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | REVIEW |
| Run control | ACTIVE |
| Current / last attempt | null; last=A2 |
| Current candidate | C2 DONE |
| Leases | Worker reservation; reviewer stopped/released |
| Active findings / obligations | F1..3 verification obligations до подтверждения; затем ∅ |
| Historical findings | Original three findings сохранены |
| Authorization state | One AUTH findings=[F1,F2,F3], consumed by A2 |
| next_action | integrate_when_all_obligations_pass |
| Допустимая следующая команда | integrate |

**Критерий завершения всего сценария:** Один worker cycle, три отдельные closure proofs; частичный PASS не закрывает остальных; закончить INTEGRATED.

#### Q05. No-change BLOCK

**Полный путь:** `BOOT→C1→repair A2 BLOCK files=[]→stop+clean audit→finalize restore`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | BLOCKED |
| Run control | BLOCKED |
| Current / last attempt | null; last=A2 BLOCKED |
| Current candidate | C1 retained |
| Leases | A2 released; no live writers |
| Active findings / obligations | Исходный F1/scope blocker остаётся active |
| Historical findings | Attempt A2 immutable; old findings retained |
| Authorization state | Old consumed; new authorization absent |
| next_action | replan_repair_scope |
| Допустимая следующая команда | authorize-repair after cause/scope decision |

**Критерий завершения всего сценария:** Новая auth→A3 DONE→C2 PASS→INTEGRATED; проверить также initial implement без C1.

#### Q06. BLOCK с непустым валидным write-set

**Полный путь:** `BOOT→A1 BLOCK external E, focused PASS→strict audit→preserve`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | BLOCKED |
| Run control | BLOCKED |
| Current / last attempt | null; last=A1 BLOCKED |
| Current candidate | C1 CONTINUATION |
| Leases | Reservation only; writer stopped |
| Active findings / obligations | External E active |
| Historical findings | Original BLOCK unchanged |
| Authorization state | CONT auth applied, no repair auth |
| next_action | review_or_authorize_continuation_repair |
| Допустимая следующая команда | prepare-review / authorize-repair |

**Критерий завершения всего сценария:** После valid repair и E resolution получить DONE C2→fresh required reviews→INTEGRATED; direct integrate C1 rejects.

#### Q07. HANDOFF

**Полный путь:** `BOOT→A1 HANDOFF; variants files=[] and owned nonempty→finalize`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | BLOCKED |
| Run control | BLOCKED |
| Current / last attempt | null; last=A1 HANDOFF |
| Current candidate | Prior C0 or new C1 CONTINUATION per audited disposition |
| Leases | Stopped/released or safe reservation; never unknown released |
| Active findings / obligations | Remaining-work/external obligation active |
| Historical findings | HANDOFF immutable |
| Authorization state | Continuation auth only for valid preserve |
| next_action | resume_authorized_work |
| Допустимая следующая команда | authorize-repair/retry after qualified base |

**Критерий завершения всего сценария:** Fresh A2 finishes work→DONE→review→integrate; HANDOFF itself not success.

#### Q08. Внешний/out-of-scope blocker

**Полный путь:** `BOOT→worker BLOCK E→preserve; separate authorized environment/resource resolution`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | BLOCKED |
| Run control | BLOCKED |
| Current / last attempt | null |
| Current candidate | C1 CONTINUATION |
| Leases | No writer; reservation tracked |
| Active findings / obligations | E remains until exact resolution evidence |
| Historical findings | No fake criterion resolution |
| Authorization state | Separate environment authority, not silently broader ticket auth |
| next_action | resolve_external_blocker |
| Допустимая следующая команда | TARGET: resolve-blocker with evidence |

**Критерий завершения всего сценария:** Required suite rerun on correct candidate; failed E never excluded only for convenience; repair/DONE/review/integrate.

#### Q09. Quarantine + reconciliation

**Полный путь:** `BOOT→declared/actual lease mismatch→quarantine→stop proof→typed reconcile`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | BLOCKED or CANDIDATE |
| Run control | RECOVERING until all reuse proofs PASS |
| Current / last attempt | null; last quarantined attempt retained |
| Current candidate | No candidate until proof; then audited C1 |
| Leases | quarantined→reservation/released only with proof |
| Active findings / obligations | Violation active until exact scope/provenance adjudication |
| Historical findings | Original violation retained |
| Authorization state | Reconciliation authorized, no scope widening |
| next_action | finalize_reconciled_attempt |
| Допустимая следующая команда | TARGET: finalize/reconcile attempt |

**Критерий завершения всего сценария:** Legacy create repair and generic stopped lost variants complete to review/integrate; failed proof stays explicit quarantine.

#### Q10. Stale/forked provenance

**Полный путь:** `BOOT→C1→F1; try foreign source or wrong base or unrelated create lineage`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | Unchanged previous state |
| Run control | Unchanged |
| Current / last attempt | Unchanged |
| Current candidate | C1 unchanged |
| Leases | No new lease |
| Active findings / obligations | F1 remains |
| Historical findings | Unchanged |
| Authorization state | Invalid auth/packet not published |
| next_action | rebuild_candidate_bound_plan |
| Допустимая следующая команда | authorize-repair with exact current source |

**Критерий завершения всего сценария:** Reject before READY/dispatch; correct packet then full repair→integrate; verify no orphan active auth.

#### Q11. Finding без ticket binding

**Полный путь:** `BOOT→C1→registered single-ticket review return refs=[global criterion]`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | REVIEW/BLOCKED per verdict |
| Run control | BLOCKED on accepted BLOCK |
| Current / last attempt | null |
| Current candidate | C1 |
| Leases | Reviewer released only after accepted strict ingest |
| Active findings / obligations | Canonical F1 bound to ticket/candidate; raw refs unchanged |
| Historical findings | ∅ |
| Authorization state | Ready for valid auth, not stranded |
| next_action | triage_current_findings |
| Допустимая следующая команда | authorize-repair |

**Критерий завершения всего сценария:** Either canonicalize exact registered subject safely or reject before ingest with exact missing-field remedy; corrected path must reach INTEGRATED.

#### Q12. Finding rebind recovery

**Полный путь:** `Legacy frozen current review findings lack ticket; read-only classify→owner event→replay`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | BLOCKED |
| Run control | BLOCKED |
| Current / last attempt | null; last returned worker |
| Current candidate | Exact unchanged legacy candidate |
| Leases | No release without stop proof |
| Active findings / obligations | Exact re-bound current set |
| Historical findings | Original return+reported refs immutable |
| Authorization state | New auth possible after binding event |
| next_action | authorize_current_findings |
| Допустимая следующая команда | authorize-repair |

**Критерий завершения всего сценария:** Replay event no-op; conflicting ticket/candidate/hash rejected; next repair/review/integrate succeeds.

#### Q13. Historical vs active findings

**Полный путь:** `BOOT→C1 F1/F2→C2 F3; create current projection and carry-forward obligations`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | REVIEW |
| Run control | BLOCKED |
| Current / last attempt | null; last current worker |
| Current candidate | C2 |
| Leases | No live writers |
| Active findings / obligations | F3 current; unresolved F1/F2 verification debt, not silent resolved |
| Historical findings | F1/F2 old-subject history |
| Authorization state | New auth references current resolved mapping, not arbitrary old finding |
| next_action | resolve_current_findings_and_debt |
| Допустимая следующая команда | authorize-repair / targeted re-review |

**Критерий завершения всего сценария:** Close all debts only with proof; integration rejects unresolved historical concern affecting current candidate.

#### Q14. Duplicate worker return / review ingest

**Полный путь:** `BOOT→dispatch twice→same return twice→same review twice→conflicting replay`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | State equals first valid publication |
| Run control | Unchanged |
| Current / last attempt | One registered attempt, no respawn |
| Current candidate | One candidate |
| Leases | No duplicate lease/release |
| Active findings / obligations | No duplicate findings |
| Historical findings | One historical record per content/event |
| Authorization state | Consumption count=1 |
| next_action | Original valid next_action |
| Допустимая следующая команда | Proceed to candidate/integrate; replay has no side effect |

**Критерий завершения всего сценария:** Wrong duplicate rejected uniformly by ingest and integrate; retry after later revisions returns immutable prior result, not new authority.

#### Q15. Lost worker / timeout

**Полный путь:** `BOOT→PREPARED/native spawn uncertain→timeout→LOST→stop/reuse audit`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | BLOCKED |
| Run control | BLOCKED/RECOVERING |
| Current / last attempt | null; last=A1 LOST |
| Current candidate | Prior C0 or qualified partial snapshot, never guessed DONE |
| Leases | quarantined until liveness proven; then explicit disposition |
| Active findings / obligations | Termination/liveness issue active until reconciled |
| Historical findings | Partial return/files retained |
| Authorization state | Fresh retry/repair only after reconciliation |
| next_action | reconcile_attempt_liveness |
| Допустимая следующая команда | TARGET: finalize-lost-attempt |

**Критерий завершения всего сценария:** No-change and partial-created-file variants proceed to fresh worker and integrate; unknown writers permit explicit cancel/new isolated scope, not reuse.

#### Q16. Interrupted reviewer

**Полный путь:** `BOOT→C1→review interrupted/mutated export→stop→new review on pristine same C1`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | REVIEW |
| Run control | BLOCKED until new reviewer registered |
| Current / last attempt | null; old RV INTERRUPTED |
| Current candidate | C1 unchanged |
| Leases | Old reviewer released with proof; new one active during review |
| Active findings / obligations | Old interruption operational obligation; un-ingested findings not active |
| Historical findings | Invalid old output kept nonauthoritative |
| Authorization state | No repair based on un-ingested return |
| next_action | prepare_replacement_review |
| Допустимая следующая команда | prepare-review new attempt |

**Критерий завершения всего сценария:** New review→proper finding repair or PASS integration; old interrupted return cannot enter authoritative ingest/manual import.

#### Q17. Continuation candidate → repair

**Полный путь:** `BOOT→C1 CONT→review F1→grouped auth→repair dispatch`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | RUNNING |
| Run control | BLOCKED if E still active |
| Current / last attempt | A2 PREPARED/observed running |
| Current candidate | C1 CONTINUATION remains explicitly linked |
| Leases | Only A2 writer lease active; prior writer stopped |
| Active findings / obligations | F1 under repair; E retained |
| Historical findings | Original BLOCK/candidate history |
| Authorization state | AUTH consumed by A2 with exact C1/source |
| next_action | await_worker_return |
| Допустимая следующая команда | internal wait/ingest |

**Критерий завершения всего сценария:** Complete A2 return, not stop at dispatch: nochange→restore C1, partial→C2 CONT, DONE allowed only with required proofs; final integration after debt closure.

#### Q18. Continuation → DONE → review

**Полный путь:** `BOOT→C1 CONT→E resolution→repair A2 DONE→C2→all required PASS`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | INTEGRATED |
| Run control | ACTIVE |
| Current / last attempt | null; last=A2 |
| Current candidate | C2 DONE/INTEGRATED |
| Leases | All released |
| Active findings / obligations | ∅ |
| Historical findings | C1 original BLOCK stays; E resolved with evidence |
| Authorization state | Repair auth consumed; continuation auth remains history |
| next_action | schedule_next_or_g4 |
| Допустимая следующая команда | ready-ticket/gate |

**Критерий завершения всего сценария:** Direct integrate CONT rejected; DONE label alone cannot erase unresolved E from prior lineage.

#### Q19. Critical review barrier

**Полный путь:** `BOOT critical ticket→DONE C1→routine PASS; missing/failed critical axis→blocked`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | REVIEW |
| Run control | BLOCKED while required axis pending/failed |
| Current / last attempt | null |
| Current candidate | C1 |
| Leases | Worker reservation; independent reviewer grants qualified |
| Active findings / obligations | Missing axis/contamination obligation remains |
| Historical findings | Routine PASS retained, not sufficient |
| Authorization state | No implicit user-assisted bypass |
| next_action | complete_required_critical_axis |
| Допустимая следующая команда | prepare-handoff purpose=critical_axis |

**Критерий завершения всего сценария:** Qualified fresh critical PASS closes axis; integrate ticket releases reservation; does not jump directly to final ACCEPT.

#### Q20. Successor run

**Полный путь:** `BOOT predecessor→quiesce→cancel→owner-approved successor manifest→new BOOT`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | Old unfinished tickets CANCELLED; new PLANNED/READY |
| Run control | Old CANCELLED; new ACTIVE/BLOCKED per inheritance |
| Current / last attempt | New attempt namespace only |
| Current candidate | Verified inherited candidate/base, not inherited DONE verdict blindly |
| Leases | Old released or isolated under explicit scope; new ownership explicit |
| Active findings / obligations | Inherited unresolved concerns explicit |
| Historical findings | Predecessor history byte-identical |
| Authorization state | Parent scope decision and import manifest bound |
| next_action | qualify_inherited_artifacts_then_execute |
| Допустимая следующая команда | TARGET: publish-successor / normal bootstrap |

**Критерий завершения всего сценария:** Proceed one new ticket to INTEGRATED; missing resource or bad parent hash blocks before READY; old run never reopened.

#### Q21. Wave transition

**Полный путь:** `BOOT→wave tickets repair/review/integrate→aggregate wave-close`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | Wave members INTEGRATED |
| Run control | ACTIVE only if required debts closed |
| Current / last attempt | null |
| Current candidate | Common frozen wave candidate |
| Leases | No live/reserved required writers or pending effects |
| Active findings / obligations | ∅ for wave obligations |
| Historical findings | All prior findings retained with outcomes |
| Authorization state | All used auth consumed; stale unused revoked |
| next_action | next_wave_or_g4 |
| Допустимая следующая команда | TARGET: finalize-wave / ready-ticket |

**Критерий завершения всего сценария:** Next wave dependencies see only reviewed current results; mid-wave cancellation/pending axis prevents closure.

#### Q22. Crash/restart между durable steps

**Полный путь:** `BOOT through entire lifecycle; inject fault at every write boundary and replay`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | Last committed valid ticket state or reconciled successor state |
| Run control | RECOVERING until exact effects resolved |
| Current / last attempt | Known registered attempt; unknown spawn not duplicated |
| Current candidate | Exact proven existing candidate; no guessed link |
| Leases | No premature release/reuse |
| Active findings / obligations | No dropped/duplicate findings |
| Historical findings | Immutable objects preserved |
| Authorization state | Exactly-once logical consumption despite retries |
| next_action | reconcile_exact_boundary |
| Допустимая следующая команда | recover + typed reconcile/finalize |

**Критерий завершения всего сценария:** For each fault point recover to INTEGRATED/ACCEPTED or explicit externally blocked/cancelled without data loss; not only JSON validity.

#### Q23. Idempotent recovery

**Полный путь:** `BOOT→each recovery once→other valid progress→same recovery replay`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | Current advanced state unchanged |
| Run control | Unchanged |
| Current / last attempt | No rollback of current attempt |
| Current candidate | No rollback to older candidate |
| Leases | No reopen of released lease |
| Active findings / obligations | No resurrection/invalidation duplication |
| Historical findings | Original recovery event retained once |
| Authorization state | No reconsumption |
| next_action | Current next_action unchanged |
| Допустимая следующая команда | Continue current eligible action |

**Критерий завершения всего сценария:** Replay of terminate/preserve/closure/reconcile/manual-import/adjudicate does not require old mutable post-state forever; conflicting args rejected.

#### Q24. Integration после многих repairs

**Полный путь:** `BOOT→create A1→modify A2→preserve-path A3→modify A4→final C4 all reviews`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | INTEGRATED |
| Run control | ACTIVE |
| Current / last attempt | null; last=A4 |
| Current candidate | C4 DONE/INTEGRATED |
| Leases | All released |
| Active findings / obligations | ∅ |
| Historical findings | Each finding provenance/resolution retained |
| Authorization state | Each auth once, source chain complete |
| next_action | schedule_next_or_g4 |
| Допустимая следующая команда | ready-ticket/gate |

**Критерий завершения всего сценария:** No blanket invalidation, no stale/fork edge, no remaining same-ticket reservation; complete G4/G5.

#### Q25. Authorize accepted ⇒ next dispatch admissible

**Полный путь:** `BOOT→F1→repeat unchanged repair or bad scope/source attempt at authorization`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | Previous REVIEW/BLOCKED, not new READY |
| Run control | Unchanged |
| Current / last attempt | Unchanged |
| Current candidate | Current C1 |
| Leases | No new active lease |
| Active findings / obligations | F1 still active |
| Historical findings | Unchanged |
| Authorization state | No doomed authorization published |
| next_action | repair_preflight_error |
| Допустимая следующая команда | Correct AttemptPlan then authorize |

**Критерий завершения всего сценария:** After valid plan, immediate dispatch succeeds unless separately recorded external drift; authorization replan is audited.

#### Q26. Cancel/quiesce/recover fences

**Полный путь:** `BOOT→READY→cancel request→try dispatch; finalize CANCELLED→try recover/amend`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | Before finalize unchanged; then CANCELLED |
| Run control | QUIESCING then CANCELLED, never reopens |
| Current / last attempt | No new attempt after quiesce |
| Current candidate | History only |
| Leases | Stopped and explicitly released for terminal |
| Active findings / obligations | Historical blockers preserved as history |
| Historical findings | Unchanged |
| Authorization state | Pending auth revoked/suspended per cancellation |
| next_action | stop_reconcile_then_cancel / terminal |
| Допустимая следующая команда | cancel finalize / new explicit successor |

**Критерий завершения всего сценария:** Every prohibited mutator fails before any document/ledger/product write; no duplicate spawn.

#### Q27. Allow/deny/identity/risk mismatches

**Полный путь:** `BOOT→packet allow∩deny, wrong ticket/epoch, criteria/risk downgrade, undefined route`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | Unchanged before registration/ingest |
| Run control | Unchanged |
| Current / last attempt | No wrong-identity active attempt |
| Current candidate | Unchanged |
| Leases | No invalid lease |
| Active findings / obligations | No wrongly attributed finding/return |
| Historical findings | Invalid payload retained only diagnostic |
| Authorization state | No false consumption |
| next_action | correct_packet_or_return |
| Допустимая следующая команда | dispatch/ingest only after exact correction |

**Критерий завершения всего сценария:** Exercise all mismatches through public CLI then complete valid ticket; not helper-only schema check.

#### Q28. Preserve hops и source normalization

**Полный путь:** `BOOT→create C1→repair using exact finding review source→BLOCK preserve C2→nochange close→new repair`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | BLOCKED at closure checkpoint |
| Run control | BLOCKED until E resolution |
| Current / last attempt | null; last blocked attempt |
| Current candidate | C2 CONTINUATION retained |
| Leases | No abandoned active writer |
| Active findings / obligations | Current findings/E retained |
| Historical findings | All source hops immutable |
| Authorization state | Source review normalized to correct worker/candidate once |
| next_action | authorize_candidate_bound_repair |
| Допустимая следующая команда | authorize-repair |

**Критерий завершения всего сценария:** No command later rejects its own accepted normalized source; continue to DONE C3/review/integrate.

#### Q29. Несколько reviews одного candidate

**Полный путь:** `BOOT→C1→RV-A PASS+RV-B BLOCK or UNVERIFIABLE; try integrate A`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | REVIEW |
| Run control | BLOCKED |
| Current / last attempt | null |
| Current candidate | C1 |
| Leases | Review leases stopped; worker reservation |
| Active findings / obligations | Blocking RV-B obligations active |
| Historical findings | Both immutable verdicts |
| Authorization state | Repair auth covers accepted blocking set |
| next_action | adjudicate_or_repair |
| Допустимая следующая команда | adjudicate / authorize-repair |

**Критерий завершения всего сценария:** No cherry-picking PASS. Legit adjudication updates issue+finding projections consistently, then fresh relevant review and integration.

#### Q30. Stale review/finding после замены candidate

**Полный путь:** `BOOT→C1 review F1→repair C2→attempt stale ingestion/authorization using C1 evidence`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | Unchanged C2 state |
| Run control | Unchanged |
| Current / last attempt | Current attempt unaffected |
| Current candidate | C2 |
| Leases | No new stale lease |
| Active findings / obligations | Current findings only; old concern may be verification debt |
| Historical findings | C1 review remains historical |
| Authorization state | Stale authority rejected or explicit revalidation required |
| next_action | revalidate_current_subject |
| Допустимая следующая команда | New review or correct candidate-bound authorize |

**Критерий завершения всего сценария:** Complete C2/C3 integration only after proof on current subject; matching ticket alone insufficient.

#### Q31. PASS с failed/not_run/unverifiable checks

**Полный путь:** `BOOT→current candidate→review/manual PASS with contradictory checks`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | Pre-ingest state unchanged |
| Run control | No false ACTIVE/ACCEPTED |
| Current / last attempt | Reviewer remains awaiting corrected evidence or safely interrupted |
| Current candidate | Unchanged |
| Leases | No release based on invalid verdict |
| Active findings / obligations | No false resolution |
| Historical findings | Invalid return diagnostic only |
| Authorization state | No integration authority |
| next_action | correct_review_evidence_or_block |
| Допустимая следующая команда | Corrected return/new independent review |

**Критерий завершения всего сценария:** Negative test for all three outcomes and required axes; corrected real PASS reaches integration/acceptance.

#### Q32. Attempt-level BLOCK cannot be overwritten via integrate

**Полный путь:** `BOOT→ingest review BLOCK bytes X→submit PASS bytes Y to every ingress`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | REVIEW/BLOCKED unchanged |
| Run control | BLOCKED |
| Current / last attempt | Review remains returned X |
| Current candidate | C1 |
| Leases | Existing correct disposition unchanged |
| Active findings / obligations | Original F active |
| Historical findings | X hash/ref/review_result unchanged |
| Authorization state | Only repair/adjudication allowed |
| next_action | triage_current_findings |
| Допустимая следующая команда | authorize-repair |

**Критерий завершения всего сценария:** Same-byte X replay harmless; Y uniformly rejected; valid new review must have new registered attempt and subject/evidence.

#### Q33. Manual BLOCK materializes repairable findings

**Полный путь:** `BOOT→integrated wave→final G5 manual BLOCK with F1..Fn`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | Affected repair targets created/reopened by authorized protocol |
| Run control | BLOCKED |
| Current / last attempt | null; manual review RETURNED |
| Current candidate | Frozen reviewed C1 |
| Leases | Reviewer released with exact receipt |
| Active findings / obligations | F1..Fn canonical, independently actionable |
| Historical findings | Raw G5 BLOCK retained |
| Authorization state | Grouped repair-wave auth possible |
| next_action | triage_g5_findings |
| Допустимая следующая команда | authorize repair-wave |

**Критерий завершения всего сценария:** Repair→targeted closes→common C2→fresh G5 PASS→G6; no stale import_manual_review loop.

#### Q34. Candidate/effect receipt integrity

**Полный путь:** `BOOT→DONE→fake SHA/wrong target/base/authority/dirty tree; or real commit then applied receipt`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | No candidate on failed proof; C1 once on valid recovery |
| Run control | BLOCKED/RECOVERING until exact proof |
| Current / last attempt | Returned producer retained |
| Current candidate | Only real audited C1 |
| Leases | Reservation safe; no unknown writer reuse |
| Active findings / obligations | Mismatch issue until reconciled |
| Historical findings | Invalid receipt not authority |
| Authorization state | Effect authority exact |
| next_action | reconcile_or_finalize_candidate |
| Допустимая следующая команда | TARGET: finalize-effect |

**Критерий завершения всего сценария:** Prepared/applied domain state agrees; applied-without-linkage repaired without new commit; uncertain→resolved supported.

#### Q35. Amendment/canonical publication atomicity

**Полный путь:** `BOOT→current docs→stale-token/same-path/conflicting amendment; live worker variant`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | Unchanged for rejected command; STALE only for accepted amendment |
| Run control | Quiesce before material rewrite; ACTIVE only after safe recovery |
| Current / last attempt | Affected writers stopped/fenced, not merely relabeled |
| Current candidate | Old candidate stale/historical |
| Leases | No overwrite while writer unknown |
| Active findings / obligations | Impact closure explicit |
| Historical findings | Every prior document/hash unchanged |
| Authorization state | Exact owner scope authority |
| next_action | recheck_affected_gates |
| Допустимая следующая команда | amend→G1/G2/G3 via valid replacement path |

**Критерий завершения всего сценария:** Failed operation changes neither canonical referenced bytes nor ledger; valid amendment returns to executable current tickets.

#### Q36. Manual interrupted/stale epoch/mismatched purpose

**Полный путь:** `BOOT→critical/G5 handoff→interrupt/takeover or wrong review packet purpose→import`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | No false INTEGRATED/ACCEPT |
| Run control | BLOCKED/RECOVERING |
| Current / last attempt | Old attempt INTERRUPTED/history |
| Current candidate | Unchanged exact candidate |
| Leases | No reuse before proof |
| Active findings / obligations | Explicit interruption/purpose gap |
| Historical findings | Old payload historical |
| Authorization state | New purpose-bound packet/attempt required |
| next_action | prepare_current_manual_review |
| Допустимая следующая команда | prepare-handoff new attempt |

**Критерий завершения всего сценария:** Old packet cannot be reinterpreted silently; fresh correctly typed review proceeds through appropriate ticket/G5 gate.

#### Q37. Semi-mode checkpoints и native waits

**Полный путь:** `BOOT semi→routine ticket→internal waits→authority-sensitive or manual checkpoint`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | Routine advances without per-ticket approval; checkpoint preserves exact state |
| Run control | ACTIVE for routine; BLOCKED for actual authority need |
| Current / last attempt | Registered exact attempt or null at real checkpoint |
| Current candidate | Frozen as appropriate |
| Leases | No new writer while checkpoint affects ownership |
| Active findings / obligations | Only genuine authority/liveness blocker |
| Historical findings | Waits not fake history of user decisions |
| Authorization state | Existing authority reused only within scope |
| next_action | internal_await OR await_owner_decision |
| Допустимая следующая команда | Native wait/reconcile OR explicit approved transition |

**Критерий завершения всего сценария:** No routine user stop from await; response to checkpoint bound to exact subject, epoch and scope. Repeat same suite with full, no safety downgrade.

#### Q38. Evidence object/export tampering

**Полный путь:** `BOOT→immutable object/export→change bytes or omit inventory entry→review/recovery read`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | No authoritative change on failed proof |
| Run control | BLOCKED with integrity cause |
| Current / last attempt | No false returned/accepted state |
| Current candidate | Unchanged verified last candidate |
| Leases | Quarantine affected access, not false release |
| Active findings / obligations | Integrity obligation active |
| Historical findings | Corrupt bytes preserved diagnostic; good original hash never remapped |
| Authorization state | No auth from unverifiable history |
| next_action | restore_verified_evidence |
| Допустимая следующая команда | Typed integrity reconciliation |

**Критерий завершения всего сценария:** Same hash path with changed bytes fails; exact complete inventory required; restore trusted copy then full review/integrate.

#### Q39. Contract output activation + inherited resource completeness

**Полный путь:** `BOOT producer/consumer graph incl proposed output and predecessor external artifact`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | Producer executable without self-input; consumer not READY until proof |
| Run control | ACTIVE independent work or BLOCKED relevant consumer |
| Current / last attempt | No consumer attempt on missing input |
| Current candidate | Verified producer/inherited candidate |
| Leases | No invalid consumer lease |
| Active findings / obligations | Missing proof/resource blocker explicit |
| Historical findings | Original binding versions retained |
| Authorization state | No silent proposed→active |
| next_action | activate_verified_output_or_resolve_resource |
| Допустимая следующая команда | TARGET: publish-contract-proof then ready-ticket |

**Критерий завершения всего сценария:** Consumer runs only after verified artifact/version availability; legacy self-input migration tested then complete consumer integration.

#### Q40. G5 repair wave and fresh common candidate

**Полный путь:** `BOOT→all tickets integrated C1→G5 BLOCK F1,F2→two dependent repairs→targeted reviews→common C3`.

| Поле | Ожидаемое состояние в checkpoint |
| --- | --- |
| Ticket status | All replacement/repair targets INTEGRATED |
| Run control | VERIFY until fresh full G5; then ACCEPT/ACTIVE |
| Current / last attempt | null |
| Current candidate | C3 common current candidate |
| Leases | No unresolved leases/effects |
| Active findings / obligations | ∅ only after all per-finding proof and fresh G5 |
| Historical findings | G5 C1 BLOCK remains historical |
| Authorization state | Group wave auth, individual consumed attempts |
| next_action | fresh_g5_then_g6 |
| Допустимая следующая команда | prepare-handoff final_g5→import→gate G6 |

**Критерий завершения всего сценария:** Old G5 PASS/BLOCK never reused on C3; G6 enforces exact current candidate fingerprint, full criteria and requested human policy.

### 7.3. Универсальные assertions после каждого durable шага

Проверять нужно не только итоговый `ACCEPTED`, но и все промежуточные сочетания состояния. Обязательны schema + cross-entity invariants, актуальность intent/publication/epoch/subject, точная candidate lineage, owner lease scope и отсутствие конкурирующих writers, content hashes immutable evidence, связь authorization с consumed attempt, согласованность raw findings и active/debt projection.

После каждого accepted transition suite должна вызвать предложенную следующую штатную команду с заранее определёнными valid inputs. После каждого rejected transition сравниваются revision, referenced file hashes и effect state: ошибка не должна оставлять новый writer, consume authorization или менять canonical bytes. Применяется и к stale owner/revision, conflicting replay и malformed partial returns.

Каждый recoverable mutator повторяется: сразу после успеха; после искусственного сбоя на каждом durable boundary; после продвижения run на следующие transitions. Same-byte retry возвращает прежний immutable result, не запускает заново внешний эффект. Changed-byte retry либо отдельный authorized новый event, либо rejection до mutation. Исторический идемпотентный ответ не является новым разрешением spawn.

Fault injection обязателен до/после immutable object write, canonical publication, effect prepare, Git commit, receipt publication, ledger replace, snapshot write, attempt registration, native spawn observation, stop observation и release. Для Git/ledger split надо отдельно проверять `commit exists / receipt missing`, `receipt exists / linkage missing`, `effect applied / candidate missing` и `unknown outcome → later proof`.

Replay model и implementation должны использовать общие guards, но ожидаемые результаты tests не должны просто копировать output reducer. Нужны независимо заданные invariants и negative cases. Простая достижимость ACCEPTED в вручную составленном JSON-графе не проверяет ни один из перечисленных отказов.

### 7.4. Runtime qualification — отдельный слой

CLI suite с synthetic runtime receipts не доказывает фактическую остановку child process, isolation конкретного Codex запуска или непрерывность orchestration loop. Для заявляемого supported runtime нужен отдельный набор настоящих spawn/wait/interrupt/restart probes с durable handles и наблюдением filesystem. Результат должен отдельно указывать capability и proof grade. Unsupported condition остаётся fail-closed/owner-assisted, а не автоматически считается equivalent supported mode.

## 8. Recovery plan для текущего Idea Scout revision 58

**Только план. Никакие recovery-команды на Idea Scout не выполнялись.** Здесь frozen revision 58 используется как доказанный baseline; перед реальным выполнением нужно сравнить его с живым run. Если live revision уже иная, этот план нельзя применять как будто состояние не менялось.

### 8.1. Подтверждённая исходная точка

| Объект | Значение из evidence |
| --- | --- |
| Run / revision / mode | 2026-09-17-idea-scout-v2-successor / 58 / semi + deep |
| Phase / control / ticket | EXECUTE / BLOCKED (review_not_pass) / T02-R17 BLOCKED; risk=critical |
| Current worker | T02-R17-WORKER-05; RETURNED; исходный status=BLOCKED; lease active как candidate reservation |
| Continuation candidate | ef8da4ff49cc7f8014d90f463acf8319ad7c1335 |
| Tree / base | eb86d12ccb6f75f5337c18d0480f5ae16c131721 / 9aa5501870352b87538355d14bb68dbde544c3ed |
| Preservation | t02-r17-worker-05-continuation-commit-01 уже applied; continuation-auth-T02-R17-WORKER-05-01 уже применена |
| Current review | T02-R17-REVIEW-CODE-05; RETURNED / BLOCK; reviewer lease released |
| Review return SHA-256 | e977b0f75bde0456a1a644fb82ad683f31ae10926b804b5798b8912ddc5dcd1c |
| Review packet SHA-256 | e8b28341a5e2202e22c0281de105780bc92b9d5079f7104df9475bdf26001a00 |
| Stored next_action | await_blocked_candidate_review — устарел после принятия этого review |
| Findings | 21 всего: 10 T02 code = 3 current + 7 historical; ещё 11 design |
| Issues | 17 blocking; lifecycle.issue_refs содержит 7 operational/verdict refs, не всю активную проекцию |
| External blocker | issue-62c0073109c9529a; failed T02-OFFLINE-SUITE / C-V2-01; не закрыт свежим PASS evidence |

Источник таблицы: `evidence/state/successor/rev-058-ledger.json`, `evidence/objects/e977b0f75bde0456a1a644fb82ad683f31ae10926b804b5798b8912ddc5dcd1c`, continuation receipt `objects/839179…`. Ledger подтверждает сохранённые результаты, но не текущее физическое состояние checkout или наличие живого процесса в момент будущего recovery.

Три current implementation findings — **утверждения accepted review05**, не результаты независимого запуска продуктового кода в этом audit:

| Finding | Содержание accepted review | Mirrored issue |
| --- | --- | --- |
| finding-e977b0f75bde-1 | Нельзя persist/activate extraction revision с zero signals. | issue-6052c0b24e4aa5ea |
| finding-e977b0f75bde-2 | ResearchPlan JSON и normalized questions/outcomes/QUICK refs не образуют точное соответствие. | issue-1fec003177035f88 |
| finding-e977b0f75bde-3 | Неизменяемость SearchRun settings обходится через delete/recreate. | issue-97733f767ad71380 |

### 8.2. Сначала ownership, integrity и совместимость state contract

Сохранить verified backup живого ledger, objects, canonical documents и фактического Git состояния; сравнить revision/hash/owner epoch с ожидаемыми. Подтвердить остановку Worker05 и остальных неизвестных writers, а не заключать это только из `RETURNED`. Reviewer05 уже released в ledger, но physical isolation/stop observations всё равно должны соответствовать доступным receipts. Проверить HEAD/tree/base и отсутствие посторонних изменений в authoritative и candidate workspaces. Не повторять уже applied preservation и не создавать второй «тот же» commit.

Установить hardening release с проверенной source/runtime parity. На копии сначала выполнить read-only classification и dry-run migration. Непосредственно запускать текущий `recover` как универсальное лечение нельзя: он не устраняет binding/projection defects и имеет terminal-control gap.

Отдельный обязательный шаг — решить найденные **девять self-input contract bindings**. Для T02 это ARCHITECTURE; остальные перечислены в AH-08. Недостаточно добавить `T02-R17` трём findings и оставить будущую несовместимость до T03. Требуется подтвердить по canonical design, является ли запись input specification или produced deliverable, и оформить проверяемую миграцию связей. Если смысл scope не меняется — нужен явный equivalence/provenance receipt; если меняется — owner-approved publication и affected G2/G3. Недостающие полные live canonical files не позволяют сейчас автоматически выбрать конкретную семантическую правку.

Если это изменит current publication/intent, остальные recovery events и следующий packet должны быть привязаны к новому доказанно эквивалентному/current subject. Нельзя механически переносить старое review на материально другой контракт. При material change потребуется соответствующая независимая revalidation, даже если Git SHA пока не изменился.

### 8.3. Исправить binding без переписывания original return

Добавить новый **binding-reconciliation event** с owner authority, exact old ledger hash/revision, review attempt, registered subject `T02-R17`, candidate SHA/tree, packet hash и accepted return hash. Он канонически связывает ровно три `finding-e977b0f75bde-*` и их три mirrored issues с subject текущего review05. Право добавить subject выводится из зарегистрированного review packet + ledger relation, а не из догадки по тексту finding.

Исходные `reported_affected_refs`, raw return bytes/hash, verdict=BLOCK, даты, авторство и прошлые записи не меняются. Не надо перепубликовывать «исправленный return» под тем же attempt: это нарушает immutable ingestion. Новый event однозначно объясняет, какие canonical bindings исправлены и почему. Same-byte повтор — no-op; другой candidate, чужой ticket, иной hash или owner epoch должны требовать новый допустимый plan либо rejection.

Не импортировать четыре finding из прерванного review04: его return не принят как authoritative, а нарушение целостности export и stop/restart относятся к отдельному эпизоду. Полезный текст не заменяет допустимый источник authority.

### 8.4. Отделить current concerns от history и не потерять незакрытую работу

Текущая candidate projection содержит три implementation findings review05. Семь старых code findings перечислены ниже. Они historical по subject/review round; это **не доказательство resolved**. Для каждого требуется resolution proof, явная supersession mapping на текущую concern либо отдельная verification obligation. Если такого доказательства пока нет, отображение может показывать «3 current + N unverified historical concerns», но не ложное «осталось ровно 3 проблемы».

`finding-f989a2c3e524-1` — сохранить raw finding; классифицировать applicability к текущему candidate и ссылку на независимое closure/supersession evidence. До доказательства не объявлять семантически resolved.

`finding-bcbdeeded833-1` — сохранить raw finding; классифицировать applicability к текущему candidate и ссылку на независимое closure/supersession evidence. До доказательства не объявлять семантически resolved.

`finding-bcbdeeded833-2` — сохранить raw finding; классифицировать applicability к текущему candidate и ссылку на независимое closure/supersession evidence. До доказательства не объявлять семантически resolved.

`finding-bcbdeeded833-3` — сохранить raw finding; классифицировать applicability к текущему candidate и ссылку на независимое closure/supersession evidence. До доказательства не объявлять семантически resolved.

`finding-bcbdeeded833-4` — сохранить raw finding; классифицировать applicability к текущему candidate и ссылку на независимое closure/supersession evidence. До доказательства не объявлять семантически resolved.

`finding-bcbdeeded833-5` — сохранить raw finding; классифицировать applicability к текущему candidate и ссылку на независимое closure/supersession evidence. До доказательства не объявлять семантически resolved.

`finding-22bf0f5a4fde-1` — сохранить raw finding; классифицировать applicability к текущему candidate и ссылку на независимое closure/supersession evidence. До доказательства не объявлять семантически resolved.

Исходные BLOCK review-verdict records предыдущих раундов можно пометить superseded как **результат старого раунда**, не переписывая verdict. Их содержательные obligations закрываются отдельно. Current review05 BLOCK остаётся активным barrier до исправлений и свежей допустимой проверки.

`attempt-T02-R17-REVIEW-CODE-04-interrupted` допускает operational closure по stop/integrity evidence и успешно принятому replacement review05: это закрывает потребность повторить прерванный review, не признаёт его discarded findings. `issue-b5315db91291e13b` о недостаточной lease Worker04 может получить supersession/closure по последующей конкретной Worker05 authority и accepted scoped execution; это не доказательство исправления всех product/resource failures.

`issue-62c0073109c9529a` **не закрывать** только потому, что появился continuation candidate или review05. По accepted Worker05 return остаётся failed offline suite: 11 failures связаны с отсутствующими evaluation-v2 resources в доступном base/вне lease. Это факт return и incident evidence, а не заново проверенное содержимое product repository. Нужна отдельная допустимая ресурсная/environment correction с новым evidence либо explicit versioned owner decision об oracle/scope. Нельзя выдать repair worker разрешение менять эти ресурсы молча.

Design findings (ещё 11 records) не входят в пользовательские «10 code findings» и не должны быть массово изменены code-currentness migration. Existing `migrate-review-currentness` для design publication нельзя использовать как универсальный invalidate-all для T02.

### 8.5. Одна authorization и один worker cycle для трёх findings

**Да, безопасно спроектировать один repair cycle для этих трёх findings.** Они происходят из одного accepted review, относятся к одному candidate и ticket. Но разрешение должно быть новой grouped authorization с `finding_refs=[…-1,…-2,…-3]`, общей candidate/intent/publication binding, одним согласованным scope и отдельными expected proofs по каждому finding.

Это не означает одну безусловную запись «всё исправлено». Worker может адресовать все три изменения за один attempt, а независимый re-review обязан дать три отдельных результата. Частично не закрытые findings остаются active/verification obligations. Historical concerns также не исчезают от membership новой группы.

Не переиспользовать auth05/auth06 или менять их содержимое: auth06 уже связана с Worker05. Новый repair должен опираться на continuation `ef8da4…` с producer Worker05. Допустимый source review нормализуется в этот же candidate identity до authorize, dispatch и возможного preserve; разные команды не должны снова расходиться в трактовке source.

В текущей Worker05 lease только три modify paths: `migrations/009_v2_core.sql`, `tests/test_v2_migrations.py`, `tests/test_v2_store.py`. Нельзя заранее объявить их достаточными для всех трёх новых implementation findings: store/types implementation тоже может потребовать правок. Exact next allowlist надо вывести из approved repair plan и actual product source, а затем проверить относительно ticket zone, deny rules и write ownership. Этот audit не видел product source и не подменяет такой анализ.

Все восемь criteria T02 (`C-V2-01`, `03`, `07`, `09`, `10`, `11`, `19`, `20`) и их required checks сохраняются, кроме explicit versioned authority change. Группировка findings не уменьшает критерии DONE.

### 8.6. Точное целевое состояние перед следующим dispatch

Ниже состояние **предлагаемого hardened протокола**, а не команда редактирования v1.0.11 JSON. Новые имена action/status — reference-model обозначения; реализация может сохранить совместимые enums, но должна обеспечивать те же инварианты.

| Поле | Обязательное значение / условие |
| --- | --- |
| Phase / control | EXECUTE / BLOCKED while external blocker retained |
| Ticket | READY_FOR_AUTHORIZED_REPAIR (READY plus explicit authorization in compatible representation); никакая другая работа автоматически не разрешается |
| Current live worker / last worker | Нет текущего writer; last_worker_attempt=T02-R17-WORKER-05 |
| Current candidate | ef8da4ff49cc7f8014d90f463acf8319ad7c1335; quality=CONTINUATION; tree=eb86d12ccb6f75f5337c18d0480f5ae16c131721 |
| Old worker lease | released only after actual stop and clean-candidate audit |
| Current review | REVIEW-CODE-05 RETURNED/BLOCK, lease released, exact accepted hashes сохранены |
| Current findings | Exactly three current candidate-bound review05 findings; unresolved old concerns separately retained as verification obligations, not silently resolved. |
| External / other obligations | issue-62c0073109c9529a остаётся; остальные operational/history obligations классифицированы evidence-bound, без blanket invalidation |
| Authorization | One new, unused, grouped, scope/candidate/epoch-bound repair authorization with individual proof obligations. |
| Operations | No prepared/uncertain effect; original preservation op remains applied, not repeated. |
| next_action | dispatch_authorized_repair_with_retained_blocker (proposed executable action) |
| Следующая команда | dispatch exact preflighted packet once, then native spawn and internal wait. |

Перед выдачей READY общий admission должен полностью проверить exact next packet: source candidate, proposed scope/deny, checks, risk/route, subject, fresh owner epoch, no incompatible live leases, no prepared/uncertain effects и одноразовую consumption новой authorization. Освобождение old reservation — только после фактического stop + clean-candidate audit; не выводится из готовности authorization автоматически.

Run может оставаться BLOCKED внешней причиной и при этом иметь **одно явно разрешённое ограниченное действие** — repair текущих implementation findings. Это именованное исключение к central guard, а не разрешение любому dispatch в BLOCKED/QUIESCING run. Readiness здесь «готов к данному authorized repair», не «все blockers исчезли».

Неизвестны заранее и не должны быть выдуманы: новый revision number, authorization ID, next packet hash, точный allowlist, live process/Git observations и owner-approved contract migration. Их получают при подготовке реального evidence-bound перехода. Frozen hashes выше остаются проверяемыми исходными anchors.

### 8.7. Как continuation возвращается в обычный lifecycle

После регистрации и единственного native spawn оркестратор остаётся во внутреннем bounded wait/reconcile loop. Возврат проходит единый identity/semantic admission и actual owned-write audit.

Если implementation fixes сделаны, но внешний offline blocker всё ещё воспроизводится, **DONE недопустим**: новый valid nonempty write-set можно сохранить очередным CONTINUATION при строгих preserve proofs; no-change BLOCK должен штатно восстановить текущий continuation. Это именно те соседние пути, которые v1.0.11 сейчас не замыкает. Нельзя просто дать continuation label=ordinary candidate ради следующего integrate.

Чтобы перейти к ordinary DONE candidate, нужно закрыть actual required checks/criteria и сохранить новый qualified commit с доказанной lineage. Тогда требуется fresh independent review текущего SHA, отдельная проверка трёх repaired findings и применимых historical obligations, а также все required axes/barriers для critical T02. Если critical transport manual, AH-09 обеспечивает тот же общий finding/integration lifecycle; это не повод прыгнуть прямо в final ACCEPT.

Только после всех required PASS и разрешения blocking obligations выполняется integrate. Он закрывает candidate reservation и конкретные доказанно resolved findings, сохраняет original BLOCK/history и выводит корректный next action. Переход к T03 отдельно проверяет dependency T02=INTEGRATED, current contracts/deliverables, наследованные resources и wave/run barriers. Финальный G5 всего run не подменяется ticket-level critical review.

## 9. Recommended release scope

### 9.1. Почему v1.1.0, а не очередной v1.0.12

[REVIEWER VERDICT] Номер версии сам по себе не техническое доказательство. Но предложенный scope меняет semantic contract состояния: explicit candidate/projection, grouped repair, unified manual review, total finalization, effect reconciliation и auditable legacy migration. Представлять это только как patch одного missing binding было бы вводящим в заблуждение.

**Рекомендуется v1.1.0 с ограниченным structural refactor.** Существующие CLI можно оставить совместимыми там, где старый контракт безопасен; старые ambiguous states должны получать диагностику/migration, а не скрытое «новая версия теперь всё принимает». Две цельные области — central admission/projection и evidence-bound finalization — предпочтительнее десятка дополнительных специальных проверок.

Emergency v1.0.12 имел бы смысл лишь как fail-closed containment: запрет известных unsafe paths, проверка immutable writes и точная диагностика несовместимого state. Такой patch не удовлетворяет запросу на systematic hardening и сам по себе не даёт допуска продолжать полный T02 lifecycle. Предпочтение — не делать эту промежуточную эксплуатационную ветку без необходимости.

### 9.2. Definition of done hardening release

Release принимается только при выполнении следующего общего gate:

1. Все P0 и P1 fixes проверены независимым code/state-machine review; interface docs, schema и executable guards описывают один и тот же контракт. Strong guards не ослаблены ради удобного прохождения тестов.
2. Q01–Q40 реализованы полными исполнимыми сценариями с промежуточными assertions и обязательным продолжением, включая критические отрицательные случаи P01–P32. Диагностический успех старого harness не подменяет новый regression PASS.
3. Полный release test package воспроизводим из поставляемого source, включая experiments/fixtures/upstream-зависимости или их явно комплектные replacements. Missing imports/fixtures не скрываются в зелёном итоговом количестве.
4. Durable failpoints и idempotent/conflicting retries квалифицированы для всех mutation families; Git/receipt/ledger split и registration/spawn split имеют проверенные recovery paths.
5. Frozen rev58 и retained legacy snapshots проходят read-only diagnosis и explicit migration rehearsal. Не переписаны raw returns, verdicts, history и actual product files. Ambiguous semantics имеют owner-approved decision либо остаются blocking.
6. Проверены packaged/runtime file hashes и фактический supported Codex workflow: spawn, bounded wait, interruption, stop evidence и currentness barriers. Неподдерживаемые runtime capabilities явно ограничены, а не объявлены эквивалентными строгому режиму.

До live resume должны быть сохранены исходный snapshot, migration receipt и понятный forward-recovery/abort path. Во время canary полезно проверять invariants на каждом transition, а не ждать общего финального code review. Последующий новый successor создаётся из-за принятого изменения scope/новой разработки, не для избавления от неудобной history.

### 9.3. Наибольшее снижение риска

Максимальную отдачу дадут не отдельно rebind command или удобная grouped authorization, а **единый admission + projection**, **общая finalization/effect completion** и **реальное E2E/fault qualification**. Они одновременно устраняют root нескольких incidents и заставляют будущий transition доказывать совместимость с соседями. Immutable publication и all-required-review barrier добавляют необходимую safety-сторону: система не должна лишь перестать блокироваться ценой ложного успеха.

## 10. Residual risks и итоговая оценка зрелости

### 10.1. Что остаётся вне доказательств этого audit

В пакетах нет полного live product repository, всей истории executable v1.0.6–v1.0.10, полного installed runtime, всех missing release fixtures и фактического native Codex execution trace. Поэтому нельзя подтвердить current checkout integrity, заново доказать или опровергнуть три implementation finding, объяснить каждое решение старого owner либо подтвердить полную заявленную runtime/source parity. Проверены hashes доступных архивных объектов и manifest-listed файлов, а не недоступных live файлов.

Внешний runtime может прервать оркестратор, потерять handle, не остановить child tools моментально или не дать наблюдение фактической isolation. Skill способен правильно зарегистрировать неопределённость, не повторить опасный spawn и остановиться fail-closed; он не может превратить отсутствие наблюдения в доказательство. MANUAL_ATTESTED_CLEAN не следует выдавать за автоматически доказанный STRICT_FRESH. Инвентаризация export и owner attestation нужны, но не дают абсолютной OS-level sandbox guarantee.

Есть также неизбежные границы файловой системы, Git и внешних операций: сбой между двумя durable domains возможен. Исправление должно делать его обнаруживаемым и безопасно завершаемым, а не обещать, что split никогда не случится. Race между полученным stop/audit receipt и новой внешней записью ограничивается authority/lease/runtime controls; Python helper сам по себе не защищает от злонамеренного владельца компьютера.

Даже полностью корректная orchestration не докажет правильность продуктового oracle. Failed offline suite из-за отсутствующих resources может быть истинным external blocker, ошибкой доставки dependencies или спором о scope; это нужно разбирать по actual product evidence. Qualified lifecycle должен честно довести до этого содержательного решения, а не устранить failure label.

### 10.2. Инженерный verdict по шести вопросам

**1. Продолжать Idea Scout на v1.0.11 безопасно?** Нет для нового T02 worker и дальнейшей интеграции. Безопасная граница сейчас — read-only inspection, сохранение evidence и подготовка hardening/migration. Известный binding bug — только один из нескольких непосредственно примыкающих gaps.

**2. Нужен сначала hardening release?** Да. Исправления должны включать не только текущий rebind, но и обязательные соседние repair/continuation/effect/review/manual/fencing пути. Иначе этот run снова проверит очередной отсутствующий переход уже на продуктовой работе.

**3. v1.0.12 или v1.1.0?** v1.1.0 как один совместно проверенный hardening scope с versioned state migration. Не full rewrite. Patch только одного symptom не соответствует установленным root causes.

**4. Что сильнее всего снижает риск?** Shared admission и cross-state invariants; explicit current candidate и active/debt projection; total attempt/effect completion; обязательное согласованное review barrier; полные executable lifecycle tests с fault/replay injection.

**5. Какие риски невозможно устранить только внутри skill?** Фактические свойства native Codex spawn/wait/stop/isolation, непрерывность запуска при внешнем прекращении сессии и недоступные runtime observations. Внутри skill всё же необходимо устранить ложные claims и небезопасные переходы при этой неопределённости. Нельзя списывать `amend` overwrite, missing binding или conflicting integrate на внешний runtime: это собственные дефекты repo.

**6. Насколько вероятно после fixes упираться в project errors, а не orchestration?** Число или процент по одному production run и adversarial fixtures необоснованны. Если выполнены P0+P1 и полноценная Q-suite, появится существенно более сильное инженерное основание ожидать, что **покрытые** lifecycle маршруты будут доходить до содержательных project/oracle решений, а не deterministic state-machine тупиков. До реализации и qualification это лишь обоснованная цель, не достигнутый результат. Неизвестные комбинации и внешние runtime failures останутся возможны.

**Итог:** текущая система — набор ценных и местами строгих механизмов с недостаточно проверенной композицией. У неё есть хорошая база для hardening без переписывания; оснований считать v1.0.11 зрелой, замкнутой state machine пока нет. Принимать v1.1.0 следует по доказанной таблице переходов и recovery, а не по числу прошедших локальных тестов или отсутствию следующего инцидента в одном удачном запуске.

## Приложение A. Воспроизводимость и комплектность доказательств

| Входной архив | SHA-256 |
| --- | --- |
| autopilot-hardening-source.zip | 128a729e1baea7d38e95a6af80c204c8b33e56d460a1065301f1290350c394c1 |
| autopilot-hardening-evidence.zip | 3ff2fd367680aa2066007fe66c2ded8f7835561698e4dc4a9576f6e283dc5772 |

Source manifest декларирует v1.0.11 и commit `642dc87693374cc03be407cc302cbcb136576713`. Все 59 manifest-listed files совпали по bytes/hash; все 57 файлов evidence SHA256SUMS также совпали. Это проверка целостности предоставленного пакета, а не независимое подтверждение Git commit origin. Полный installed runtime по одному excerpt не восстанавливается.

Официальный test command из source root:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v
```

Фактический результат: 80 reported entries, из них 71 pass, 2 failures, 6 errors и 1 skip. Все восемь unsuccessful entries связаны с отсутствующими в packet imports/fixtures; пять errors — failed import placeholders. Поэтому нельзя ни назвать полную suite зелёной, ни представить эти восемь случаев как восемь доказанных ошибок semantics самого ledger. Skip — opt-in legacy production checkpoint audit. Полный log приложен.

Независимые probes запускаются после распаковки source archive:

```bash
PYTHONDONTWRITEBYTECODE=1 python adversarial_probes.py   --source-root /absolute/path/to/autopilot-hardening-source   --output-dir /absolute/path/to/new-disposable-probe-results
```

Output directory должна быть новой. Нужны Python и Git; harness использует supplied неизменённый `tools/ledger.py`, а не исправленную копию. Он создаёт только disposable synthetic repositories/packets/receipts. Начальные READY fixtures явно задаются для изоляции переходов; это не воспроизведение BOOT product lifecycle. P23 непосредственно вызывает production object reader; остальные пробы проверяют CLI implementations. P20 — положительный exact-retry контроль.

Финальный прогон: 32/32 observations reached, 0 harness errors; из них 31 adverse/gap observation и один положительный контроль. Один structural finding может иметь несколько таких observations. После hardening ожидания соответствующих regression tests должны поменяться; «OBSERVED» здесь означает обнаруженный текущий дефект, не безопасность программы.

В `astra-autopilot-hardening-repro.zip` находятся harness, final results/summary, 32 command traces, official test log, integrity report и frozen evidence projection. Intermediate ошибочные harness drafts/прогоны не используются как evidence и в комплект не включены. Original source/evidence archives и live product files не изменялись.

Два основных результата: `astra-autopilot-hardening-review.md` — этот audit; `astra-autopilot-hardening-findings.json` — structured implementation handoff с 13 findings, required fixes/dependencies, A–L, transition model, Q01–Q40, executed observations и proposed rev58 recovery. JSON не является исполняемым migration script и не разрешает автоматически применять recovery.
