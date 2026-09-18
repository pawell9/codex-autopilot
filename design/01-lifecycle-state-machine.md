# Run lifecycle and gates

**DECISION.** Здесь единственная нормативная state machine. Состояние run — пара `phase × control`; ticket/attempt states локальны. Это избегает десятков комбинированных состояний вроде paused-repair-review. UI-команды являются событиями, не именами состояний.

## Run states

`phase`: `PREFLIGHT → INTENT → DESIGN → PLAN → EXECUTE → VERIFY → ACCEPT`.

`control`: `ACTIVE | QUIESCING | PAUSED | BLOCKED | RECOVERING | ACCEPTED | FAILED | CANCELLED`.

- ACTIVE выполняет текущую фазу. BLOCKED ждёт конкретного внешнего условия/authority; у него есть issue ID с impact=blocking.
- QUIESCING прекращает dispatch и выясняет состояние всех in-flight операций перед pause/cancel/failure/amendment.
- PAUSED — остановка по пользователю, quota или planned handoff; next_action и resources записаны.
- RECOVERING сверяет ledger и actual environment, не исполняет product tickets.
- ACCEPTED, FAILED, CANCELLED терминальны. Terminal phase сохраняет место завершения. Новый scope после terminal → новый run, а не переписывание acceptance.

До создания валидного ledger invocation может завершиться диагностикой `UNSUPPORTED` или `BLOCKED_PREFLIGHT`; это не вымышленный persisted run. Если namespace безопасно доступен, разрешено создать ledger на PREFLIGHT/BLOCKED.

## Gates and normal transitions

| From → to (ACTIVE) | Gate / owner | Completion criterion |
|---|---|---|
| invocation → PREFLIGHT | G0 entry, orchestrator | Exact target/authority установлен; canonical namespace безопасен; существующий active run направлен на recovery |
| PREFLIGHT → INTENT | G0 capabilities, orchestrator | Cheap checks pass; required capabilities подтверждены либо есть допустимый fallback; нет blocking ownership conflict |
| INTENT → DESIGN | G1 intent, orchestrator | Current intent содержит каждое пользовательское требование и наблюдаемые criteria; provenance сохранён; material ambiguity разрешена; scope exclusions видимы |
| DESIGN → PLAN | G2 coverage, independent reviewer | Spec/contracts покрывают все active requirements без silent narrowing; assumptions названы; independent coverage verdict PASS на этой intent/spec revision |
| PLAN → EXECUTE | G3 readiness, orchestrator + plan reviewer для elevated/critical | DAG acyclic; каждый active criterion имеет ticket/oracle owner; writes/ dependencies/verification исполнимы; plan risk — максимум ticket risk и собственных integration risks; при elevated/critical plan review PASS |
| EXECUTE → VERIFY | G4 candidate | Все required tickets INTEGRATED, leases закрыты, changeset frozen; integration checks pass, blocking findings закрыты или решение об их неприменимости доказано |
| VERIFY → ACCEPT | G5 independent product acceptance | Fresh verifier PASS по всем active criteria на exact candidate+intent; обязательные risk axes PASS; snapshot integrity проверена |
| ACCEPT → ACCEPTED | G6 final record, orchestrator | Current revisions не менялись; report generated; required human acceptance имеется, если была частью intent; нет active operations/leases/blockers |

G1–G3 — методические checks, не обязательные вопросы пользователю. Явный запрос build уже разрешает routine reversible implementation и review. Human approval запрашивается лишь при новой материальной authority; существующее согласие не спрашивается повторно.

## Compact depth and planning cost

Compact path допустим, если весь run содержит ≤2 routine tickets, нет public interface change, migration, unresolved semantics или cross-ticket integration risk. INTENT/G1 остаётся; DESIGN и PLAN используют один canonical Markdown artifact с отдельными sections. Один independent reviewer проверяет coverage и readiness, возвращает отдельные G2/G3 outcomes на одной версии. Orchestrator проводит обычные последовательные transitions; G3 record переиспользует plan assessment только если G2 не изменил artifact. Выход за условия compact → full depth с affected gate invalidation. Change review и fresh G5 сохраняются.

При PLAN применять neighbour/payback test: adjacent micro-changes с общей zone, authority и dependency boundary объединять, когда dispatch/review дороже самой работы. Не объединять разные risk/ownership boundaries ради квоты. Число tickets не самостоятельная цель. Requested user checkpoints spec/plan задаются intent policy и не добавляются по умолчанию.

## Разрешённые возвраты phase

| Событие | Переход | Scope invalidation |
|---|---|---|
| Coverage/design defect | DESIGN → INTENT или DESIGN | Intent gap → INTENT; technical spec correction → DESIGN; G2 повторяется |
| Plan defect | PLAN → DESIGN или PLAN | Пересчитываются affected tickets, DAG и G3 |
| Implementation finding в G4/G5/G6 | EXECUTE/VERIFY/ACCEPT → EXECUTE | Новый repair attempt/ticket; candidate freeze снят, affected reviews stale; все accepted findings одного G5 раунда образуют repair wave; после её завершения и targeted re-reviews один новый G4/G5 |
| Contract defect в execution/final | EXECUTE/VERIFY/ACCEPT → DESIGN | Orchestrator adjudicates; новые contract versions и packets; возвращается через PLAN |
| User product amendment | Любая nonterminal phase после PREFLIGHT → INTENT | Quiesce affected work; current intent revision повышается; G1 и последующие affected gates пересмотрены |
| Только runtime environment change | Phase сохраняется | Control→RECOVERING, conditional preflight; product intent не переписывается |

Все иные phase jumps запрещены. Same-phase correction тоже transaction с reason; self-loop не заменяет gate. Amendment в PREFLIGHT сохраняется до INTENT. Terminal run amendment создаёт successor в свежем namespace через `init-successor` с типизированным manifest, привязанным к точной terminal publication и принятому evidence; live attempts/reservations не переносятся.

## Control transitions

| From | Event → to | Guard / exact next action |
|---|---|---|
| ACTIVE | pause, quota, cancellation, unsafe activity, material amendment → QUIESCING | Persist stop reason/target control; stop new dispatch; interrupt existing agents and request external runtime stop receipts |
| ACTIVE | missing authority/environment при отсутствии in-flight → BLOCKED | Есть конкретный blocker и условие снятия |
| ACTIVE | detected state mismatch → RECOVERING | Freeze dispatch; только чтение/reconciliation |
| QUIESCING | all agents/commands stopped, partial state recorded → PAUSED / BLOCKED / CANCELLED / FAILED | Цель задана событием; cancellation/failure не требуют cleanup или destructive rollback. Exact receipt, not timeout/attestation, proves stop for safe reuse |
| QUIESCING | amendment safely fenced → ACTIVE/INTENT | Новый intent принят, affected returns stale; не требуется отпускать repository ownership |
| QUIESCING | невозможно доказать остановку → BLOCKED | Leases остаются quarantined; `agent_liveness_unknown` блокирует повторное использование checkout; точное снятие через takeover/reuse protocol в 02 |
| PAUSED/BLOCKED | resume либо blocker resolved → RECOVERING | Нет автоматического продолжения по истечении времени |
| RECOVERING | schema, owner, revisions, operations, environment reconciled → ACTIVE | Phase устанавливается в earliest invalid gate; fresh agents получают новые packets |
| RECOVERING | unresolved issue → BLOCKED | Recovery report содержит exact evidence/next step |
| RECOVERING | unrecoverable corruption → FAILED | Сохранились доступные evidence; все in-flight остановлены и leases disposed; дальнейшее исполнение невозможно без угадывания. Если нельзя безопасно записать terminal ledger — read-only failure diagnostic, namespace не перезаписывается |
| ACCEPT/ACTIVE | G6 pass → ACCEPTED | Только terminal transition успеха |
| PAUSED/BLOCKED/RECOVERING | user cancel → QUIESCING | Проверить даже якобы остановленные operations; затем CANCELLED |
| ACTIVE/BLOCKED | confirmed unrecoverable run failure → QUIESCING | Record failure reason; затем FAILED, если in-flight остановлены |

FAILED означает невозможность завершить данный run безопасно, а не «исчерпан произвольный repair counter». Восстановление продукта после terminal failure — successor run с ссылкой на checkpoint; historical verdict сохраняется.

## Ticket and attempt machine

Ticket: `PLANNED → READY → RUNNING → CANDIDATE → REVIEW → INTEGRATED`.
Дополнительные состояния: `BLOCKED`, `REPAIR`, `STALE`, `CANCELLED`.

- READY — derived readiness materialized только при dispatch transaction: dependencies INTEGRATED/current, valid packet, свободная lease, required capabilities.
- RUNNING имеет один active attempt. Return DONE переводит в CANDIDATE только после schema/version/write-set проверки и orchestrator candidate commit (для no-op — existing SHA).
- CANDIDATE → REVIEW после required worker verification, фиксации immutable candidate SHA и export freeze. REVIEW → INTEGRATED после independent PASS и mechanical integration verification.
- Любой incomplete state → BLOCKED по cause; после разрешения → READY с новым attempt. Reviewer finding → REPAIR → READY; исторический attempt не меняется.
- Amendment → STALE для affected tickets/returns/reviews, в том числе ранее INTEGRATED. Уже интегрированный код остаётся evidence, но перестаёт считаться доказательством актуального criterion. Orchestrator создаёт replacement/repair ticket либо явно revalidates outcome → INTEGRATED после новых gates.
- CANCELLED — исключённый ticket с recorded scope decision либо termination reason всего run; required criterion не исчезает автоматически.
- Read-only planning/research/review tasks используют attempt records без product ticket, с `subject_ref` и packet kind.

Attempt: `PREPARED → DISPATCHED → RETURNED | LOST | INTERRUPTED`; до spawn PREPARED также может перейти в INTERRUPTED с reason `cancelled_before_dispatch` или `spawn_rejected`. RETURNED хранит role-specific structured result из [05](05-task-and-return-contracts.md): worker status, reviewer verdict либо research result. Attempt и side-effect operation — разные записи: valid return не доказывает commit/integration. Один intent helper call может последовательно validate DISPATCHED и RETURNED в одной publication при наличии matching dispatch/return evidence; отсутствие отдельного dispatch receipt не разрешает fabricated timestamps или повтор spawn. При unknown фактическом spawn применяется recovery 02.

Runtime liveness and checkout reservation are orthogonal to `attempt.state`:
the lease is only an active/quarantined/released reservation, while the
optional per-attempt runtime record is `unknown`, `running`, `stopped`, or
`not_started` and points to immutable, exact-bound receipts. Dispatch and
review preparation register a stable spawn request and increment
`attempt_registrations`; they do not spawn or increment `spawn_calls`. The
external runtime's first valid `start` does that exactly once. The receipt
flow is `start` → optional `heartbeat`/`return_observed` → `stop`; a return,
timeout, missing heartbeat, or missing runtime record never implies stop.
`not_started` is only valid when no process or return exists. Exact stop must
cover descendant writers before candidate/review qualification or reservation
release/reuse; otherwise liveness stays unknown and the reservation stays
quarantined. Exact event replay is idempotent and cannot authorize a second
spawn. These are observed external claims; the helper does not physically
spawn, supervise, enumerate, or kill native descendants.

## Failure/event dispatch

| Event | Поведение | Возобновление |
|---|---|---|
| Quota/context limit | Proactive checkpoint; QUIESCING→PAUSED с cause `quota`/`context`. Abrupt cutoff оставляет last committed ledger | Recovery проверяет незавершённые attempts/operations; quota availability conditional check; лимит не означает DONE |
| Lost worker | Attempt outcome is recorded, but runtime stays `unknown` absent an exact stop/not-started receipt; checkout reservation remains quarantined | После exact stop/reuse qualification по 02 новый retry/repair на проверенном base; old handle не обязателен |
| Failed verification | Classify evidence: implementation/contract/oracle/environment | Cause-first path [04](04-routing-and-escalation.md); зелёная нерелевантная suite не снимает finding |
| Contract defect/zone missing | Ticket BLOCKED; orchestrator исправляет contract, а не worker сам расширяет scope | New version + G2/G3 affected checks + fresh packet |
| Environment/permission failure | Block affected work; независимые safe read tasks могут продолжаться, пока control ACTIVE | Устранить tool/authority cause; model upgrade не remedy |
| Conflicting reviewers | Findings сохраняются отдельно; orchestrator сравнивает expected/actual и воспроизводит факт | Evidence adjudication → accepted finding / disproven claim / intent question; majority vote отсутствует |
| User changes requirement | Сохранить user event; quiesce affected work; version intent. При active review barrier сначала stop/integrity из 06, затем canonical publication | Impact closure по contract consumers/dependencies; replan, re-review, refreeze candidate |
| Return malformed/stale | Не интегрировать; re-request только недостающие данные или fresh inspection | Packet/version validation; gap не заполняется выдуманным результатом |
| Unsafe write or external side effect | Freeze integration, preserve evidence, scope/authority triage | Exact recovery по [06](06-safety-write-git-model.md), никогда silent cleanup |

## Checkpoint, pause and cancellation

Каждый material transition атомарен по [02](02-run-ledger-and-artifacts.md). Для эффектов с опасным повтором записывается prepared operation, после — observed receipt (02). Dispatch использует durable attempt без отдельного operation journal. Перед handoff сохраняются exact next action, candidate/base, pending operations, live leases, unresolved decisions и пути evidence. Quota может оборвать шаг до этого: recovery обязана работать и с предыдущим checkpoint.

Pause сохраняет проект и worktree. Cancel прекращает дальнейшую цель, сохраняет checkpoint и показывает уже внесённые changes; отмена цели сама по себе не разрешает удаление файлов, revert чужой работы или worktree cleanup. После выполненного stop guard из 02 CANCELLED/FAILED закрывают active attempts как INTERRUPTED, unfinished tickets как CANCELLED (с run termination reason, без подмены requirement disposition), leases как released с сохранённым partial-state fingerprint. Если reuse/stop condition из 02 не выполнено, control остаётся BLOCKED, terminal transition не выполняется. Resumption не возобновляет cancelled run скрыто.

## Human decision points

Только material intent ambiguity; новая внешняя/необратимая/cost authority; выбор относительно пересекающихся user changes; принятие scope reduction; ручной checkpoint spec/plan/final, если потребован; attestation может разрешить owner takeover при abrupt recovery, но не заменяет runtime stop receipt и не освобождает lease; setup/transfer/receipt для выбранного user-assisted critical/G5 transport по [05](05-task-and-return-contracts.md#user-assisted-criticalg5-handoff). Последний — доставка независимого review, а не дополнительное user approval результата. Пока ответ необходим, dependent work не идёт. Reversible technical choices, ordinary repair, fresh worker, local branch/commit в уже разрешённом run не требуют ритуального подтверждения; runtime approval остаётся отдельным control.

## End-to-end walkthroughs (design checks)

1. New run: G0→INTENT/G1→DESIGN/G2→PLAN/G3→ticket READY/RUNNING/CANDIDATE/REVIEW/INTEGRATED→VERIFY/G5→ACCEPT/G6→ACCEPTED.
2. G5 нашёл data loss при green tests: VERIFY→EXECUTE; repair с независимым oracle; new commit; G4→новый blind G5; старый FAIL остаётся историей.
3. Run оборван после orchestrator commit, но до ledger receipt: PAUSED/abrupt→RECOVERING; сопоставить operation ID/base/tree/commit; записать receipt один раз, не выполнять повторный commit; продолжить earliest invalid gate.
4. Amendment при работающем worker: QUIESCING; старый packet fenced; intent v2, affected evidence STALE; INTENT→DESIGN→PLAN; fresh execution; final verifier видит v2 и approved amendments, не исходный brief v1.
5. Нет безопасного recovery после чужих overlapping changes: BLOCKED с diff и точным ownership question; остальные artifacts остаются reviewable, успех не объявляется.

**Completion этого design-блока:** все gate transitions имеют owner и evidence; success достижим только через G5/G6; pause/cancel/failure не теряют partial state; каждый required failure event имеет маршрут.
