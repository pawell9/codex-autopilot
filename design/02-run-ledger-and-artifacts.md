# Run ledger and artifacts

**DECISION — OD-01, targeted revision.** JSON хранит structured orchestration state; canonical prose/spec/interfaces остаются Markdown. Один authoritative источник на каждый факт, один orchestrator writer. JSONL replay, executable JS и вручную синхронизируемые status blocks не нужны. [Adjudication](11-review-adjudication.md) объясняет исходное решение; Phase G ships the ledger schema/helper protocol described below. This does not qualify native runtime spawn, supervision, or stop behavior (reserved follow-up).

## Canonical namespace

```text
<control-root>/.autopilot/
├── owner.lock                         # fixed cooperative transaction lock
├── runs/<run-id>/
│   ├── ledger.json                    # current structured state
│   ├── ledger.prev.json               # last valid previous publication
│   ├── docs/<document-id>/<version>.md # canonical immutable prose revisions
│   ├── snapshots/<revision>.json      # selected recovery snapshots
│   ├── objects/<sha256>               # immutable evidence / ingested returns
│   ├── packets/<packet-id>.json       # immutable derived dispatch projections
│   └── views/{status,final-report}.md # generated; never state authority
└── scratch/<run-id>/<attempt-id>/      # non-authoritative inbox/temp, exact grant
```

`control-root` — постоянный canonical primary checkout из Git inventory, записанный при bootstrap. Greenfield bootstrap — [06](06-safety-write-git-model.md). Nested/bare repos не поддерживаются. Execution worktree может отличаться, ledger остаётся в control-root. Agents получают exact paths; поиск «ближайшей .autopilot» по CWD не разрешает state selection. Review/source copies располагаются по 06, вне primary source tree по умолчанию; scratch inbox не означает вложенный checkout.

Run ID path-safe и exclusive. Repository-identity owner registry plus lock allows only one nonterminal owner. Bootstrap checks for another nonterminal run before publishing. For a new scope after a terminal run, `init-successor` creates a fresh namespace from a schema-validated manifest bound to the exact predecessor control root/run/revision/terminal status/ledger hash. It records accepted decisions/qualifications, scope authority, candidate/resources, unknowns, and explicitly excludes attempts, live reservations, repair authorizations, and current pointers. A fresh owner token is required. First-time bootstrap creates the owned namespace and initial ledger; no product effect precedes publication. Incomplete namespace after failure is recovered, not overwritten. Нет mutable current/index.json и альтернативного store после потери control-root. Terminal runs read-only.

`.autopilot` исключён из product commits exact path lists. Bootstrap с имеющейся scope authority добавляет только собственную строку `.autopilot/` в resolved `.git/info/exclude`, сохраняя остальные bytes; runtime permission обрабатывается по 06. При denied exclusion фиксируется ограничение, scoped staging остаётся обязательным. `.gitignore` не редактируется автоматически. Tracked/legacy/foreign `.autopilot` требует namespace/migration решения. Exclude не backup: `git clean -fdx`/`git stash --all` и удаление checkout могут удалить/переместить state. До exclusion `stash -u` также затрагивает untracked state. Report сообщает canonical path и эти конкретные ограничения; remote backup не обещается.

## Schema and authority

`schemas/contracts.schema.json` is the shipped structural SSOT with versioned definitions for ledger/packet/return/review/acceptance and typed runtime observations. The Python stdlib helper checks the supported closed subset: types, required/unknown fields, enums, refs, arrays/maps, and discriminated branches. Unknown keyword/schema version → read-only diagnostic; no general JSON Schema engine. Dev-time oracle/parity fixtures check the subset. Semantic checks include IDs/refs, DAG, gates, owner/epoch, reservation/liveness boundaries, legal transitions, and evidence hashes.

- Envelope: `schema_version`, `run_id`, `revision`, previous publication hash, timestamps UTC, skill/policy versions. Monotonic revision задаёт порядок; timestamp не stop proof.
- Unknown major/minor принимается только явно совместимым validator; migration — отдельное versioned действие с backup. Legacy JS import вне V1.
- IDs immutable, уникальны в run; ссылки по ID, не по позиции. Optional absence = not applicable; `null` + reason/typed UNKNOWN = unknown; [] = проверенное отсутствие.
- SHA-256 над exact stored bytes docs/objects/packets; Git commit/tree SHA — candidate identity. Canonical serialization JSON refs определяется один раз helper. Hash подтверждает identity, не истинность claims.

## Minimal record model

Коллекции optional до первого использования; отсутствующая collection означает пустую только там, где это явно задано schema. Model не конструирует пустые maps на каждый вызов. Большая проза хранится в docs/objects; ниже только orchestration fields и короткие decisions.

| Record | Минимальные поля / constraints |
|---|---|
| `repository`, `owner` | control root/common-dir, initial and execution HEAD/branch/checkout, inventory/instruction refs; owner token/epoch, observed session, handoff/attestation refs. Token только у orchestrator |
| `lifecycle` | phase/control из 01, reason/issue refs, stop target; `next_action {kind, subject_refs, preconditions, read_refs}` |
| `documents`, `intent` | document ID/version/path/hash/kind; current intent revision/source refs/approved amendments; acceptance/checkpoint policy; prior accepted run refs |
| `requirements`, `criteria`, `contracts` | IDs/version/status, provenance/document section refs and hashes, criterion membership, producer/consumer/dependency refs. Exact wording/oracle/signatures в canonical Markdown; packet включает нужный exact slice |
| `decisions` | ID/type/status, concise decision/reason, authority/evidence refs, affected refs, introduced revision, supersession; large rationale → doc ref |
| `tickets` | ID/goal ref, criteria/contracts/dependencies, state, verification ref, risk/complexity, versioned `zone` (literal paths/operations/denies), current attempt, replacement refs |
| `attempts` | ID/kind/mode/subject, packet ref/hash, epoch, state из 01, route ref, exact `checkout`/base/candidate SHA, immutable execution binding/hash; optional runtime record with stable spawn request, liveness, runtime instance and observation refs; embedded lease is a separate reservation (ID, frozen scope, active/quarantined/released); return ref; repair cause/finding/hypothesis/regression refs; handoff completed/remaining/next action when needed |
| `issues` | ID/type/cause, affected refs, blocking/advisory impact, expected/actual evidence, disposition, resolution condition/owner. Unverifiable criterion не превращается в PASS при accepted risk |
| `reviews`, `acceptance` | mandate/subject SHA or doc hashes, context/isolation fact refs, verdict and immutable return refs; findings promoted to issues once; acceptance rounds reference exact intent/candidate, per-criterion outcome evidence and optional human decision |
| `operations` | Только dangerous-to-repeat effects: ID/kind/target/expected_before/intended_after/authority, prepared/applied/abandoned/uncertain, receipt/evidence refs |
| `capabilities`, `routes` | Facts/invalidation по 07; route assessment, selected binding/inherit, requested vs observed resolution, adequacy/context evidence и fallback cause |
| `evidence`, `usage` | Immutable ref/hash, source/scenario/outcome/observer/subject; observed calls/time/tokens/approvals/packet bytes, measurement source, unknown=null; budget refs |

`repairs`/`handoffs` не отдельные collections: это attempt mode/payload. `concerns`/`blockers` объединены в `issues`. Planned zone принадлежит ticket, lease — attempt/checkout. Waves/ready queue/progress/repair counts, transition listing и snapshot inventory derived; отдельные mutable collections для них отсутствуют. Material transition reason/decision сохраняется вместе с изменённым subject, не теряется из-за удаления общего transitions log. `INTEGRATED` — workflow fact, не доказательство fulfillment без current evidence.

## Canonical Markdown and projections

Orchestrator пишет новую immutable Markdown revision в docs, helper валидирует IDs/section anchors и публикует её ref/hash с новым state. Large prose не передаётся JSON string и не рендерится обратно из ledger. Текущая approved revision выбирается ledger ref; непривязанный draft после сбоя не authority. Для amendment сначала создать/version doc, затем атомарно обновить references/decisions/invalidation в ledger. Таким образом нет атомарного multi-file overwrite и двойной правды.

Любая правка referenced doc пользователем/процессом даёт hash mismatch: сохранить изменённые bytes как proposed input, остановить dependent gates, adjudicate authority, создать новую approved revision либо восстановить verified prior bytes из сохранённого evidence. Сам mismatch не approval и не разрешение молча уничтожить правку. Packet/final projection собирается только из hash-verified exact criterion/requirement sections; source wording не перефразируется ради удобства parser.

Views содержат run ID/source revision/hash/generated marker, регенерируются по status/report и gate, не на каждой transaction. Drift view не меняет intent. Потеря view не блокирует чтение canonical docs.

Successor intake is not an informal read-only convention: `init-successor` verifies the schema-validated manifest against one exact, terminal, quiescent predecessor publication under predecessor/repository/target locks, stores the manifest by hash in the new ledger, claims fresh repository ownership, and initializes a clean run namespace. Current user intent remains higher authority; unavailable prior artifacts stay explicitly unknown. Экспорт в project docs — отдельный requested deliverable; AGENTS не обновляется.

## Runtime observation protocol (Phase G)

`dispatch`, `prepare-review`, and `prepare-design-review` register an attempt,
freeze its execution binding (exact checkout/base, intent/publication,
criteria/contracts/route and packet), create a stable `spawn_request_id`, and
increment `attempt_registrations`. Registration is not a native spawn and does
not increment `spawn_calls`. The external adapter is responsible for using
that ID once and reporting immutable receipts through `observe-runtime`:
`start`, optional `heartbeat`, `return_observed`, `stop`, or `not_started`.
Only the first valid `start` increments `spawn_calls`; a registration replay
returns `existing_request_do_not_spawn_again`, while exact start receipt replay
returns `already_observed; do_not_spawn_again`. Event-ID reuse with different
bytes is rejected.

Each receipt binds run/attempt/epoch/packet/spawn request/runtime instance and
records event ID, observation time, observer/build, and coverage. `start`
sets `running`; heartbeat does not refresh or expire a lease. `return_observed`
binds the exact return hash but does not mean stop. `stop` requires the exact
instance and `descendant_writers=included`. `not_started` is only valid for an
unstarted request with no runtime instance or return. Timeout, missing
heartbeat/handle, user attestation, and process scans never infer stop; legacy
attempts without a runtime record remain readable as explicitly `unknown`.
The checkout lease is a reservation, not a producer-liveness signal. Safe
candidate/review qualification, release, and reuse require exact `stop` or
valid `not_started` evidence; otherwise the reservation remains quarantined.

The helper validates, hashes, and persists an external observation; it does
not spawn, supervise, enumerate, or kill native processes/descendants. The
receipt's observer and declared descendant coverage are therefore a trust
boundary. Phase G ships deterministic protocol/state transitions, not native
runtime qualification or conformance.

## Return ingress

Предпочтительный transport при доступной записи — exact attempt inbox в scratch. Agent пишет временный файл, затем атомарно публикует `return.json`; сообщение содержит attempt ID, status и путь, без повторения payload. Это единственное metadata write grant child вне test scratch; canonical docs/ledger/packets/objects остаются orchestrator-owned. Read-only transport возвращает message; runtime file output допустим только при qualified adapter. Полный protocol и validation — [05](05-task-and-return-contracts.md#return-transport-and-ingest).

Helper копирует validated bytes в immutable objects, вычисляет hash и публикует return ref. Scratch никогда не даёт PASS/state authority. Crash после готового файла до ingest не требует нового reviewer, если identity/integrity/stop checks позволяют импорт. Partial/stale inbox сохраняется evidence, не интегрируется. Return file хранится до успешного ingest/recovery; cleanup по 06.

## Atomic publication and intent-level API

Helper — единственный writer ledger; orchestrator вызывает intent commands с owner token/epoch и expected revision. Под fixed OS advisory lock helper rereads state, rejects stale owner/revision, creates immutable referenced payloads, validates entire proposed snapshot/transition, сохраняет valid prior publication в `ledger.prev.json`, пишет same-directory temp, flush/fsync, atomic replace ledger, sync directory. Prior backup failure отменяет новую publication. Lock release после publication. Непривязанные temp/objects после сбоя harmless; generated view failure не rollback.

**Intent-level design target**, имена не frozen CLI API:

| Command | Один model intent / completion |
|---|---|
| `dispatch` | Validate readiness + route, reserve checkout, freeze execution binding, register attempt/packet, return stable spawn ID; external runtime spawn follows once |
| `candidate` | Ingest worker return and exact runtime stop/not-started proof, run write-set audit, prepare candidate Git action; approved commit with receipt, freeze SHA, register reviewer request in one intent |
| `integrate` | Ingest review return(s) plus exact reviewer stop/not-started receipt, integrity barrier, issue adjudication refs, current PASS checks; publish INTEGRATED and release reservation only under the runtime gate |
| `gate` / `amend` / `recover` | Compound subject updates, evidence refs, invalidation и next action; details co-located in respective phase |
| `brief` / `status` | Bounded read projection без full history; brief также возвращается mutation commands |

Helper не вызывает модели, не держит agent loop/daemon и не принимает substantive review decisions. Он может выполнить ограниченную approved Git action внутри intent, **только если это сохраняет native approval boundary**. Иначе возвращает exact effect request для обычного Git tool и принимает receipt; extra round trips измеряются, не скрываются. Durable prepared/applied publications внутри одной команды не одна atomic Git+JSON transaction. Общий unsafe `transact` не agent-facing happy path.

**Happy path bookkeeping target:** ≤4 model-invoked helper calls на routine nonempty ticket от dispatch до INTEGRATED, без repairs/additional axes/environment failure. Целевой путь — 3 calls выше, четвёртый резерв для runtime receipt. Native spawn/wait/Git tool calls считаются отдельно, а internal helper publications не выдаются за zero overhead. E09 измеряет total model turns, helper calls, bytes/tokens, receipts и approvals; transport, требующий больше вызовов, не считается экономически qualified молча. Shared G0–G6/setup counts показываются отдельно и amortized, не теряются в знаменателе.

## Side effects and crash reconciliation

Prepared/applied journal только для commits, init/branch/worktree changes, landing, scoped rollback/cleanup и других действий, опасных при повторе. Pure reads, projections, return/runtime observation ingest — ordinary atomic state. Dispatch durably registers PREPARED and its stable spawn request before external spawn; dispatch replay explicitly does not authorize another spawn. Exact event replay is idempotent. A lost handle, timeout, or absent heartbeat leaves runtime `unknown`; only a later exact typed stop/not-started receipt can release the reservation. Background writing command must be included in the attempt resource inventory/runtime stop coverage.

| Crash window | Recovery |
|---|---|
| До effect prepared | Effect не должен запускаться; заново решить intent |
| Prepared, actual target unchanged | Проверить authority/expected-before; repeat с тем же operation ID только после reconciliation |
| Effect happened, receipt absent | Commit: operation trailer + old HEAD + intended tree + resulting SHA; worktree: exact path/ref/common-dir/base; init: recorded pre-bootstrap inventory и actual Git identity. Совпало → receipt без повторения |
| Partial effect / foreign drift | uncertain, target quarantine, preserve evidence; exact repair/authority resolution |
| Receipt exists, view stale | Regenerate view, effect не повторять |
| Current JSON corrupt | Validate prev/selected snapshots newest-first; восстановить лишь verified committed publication, reconcile все actual effects после неё |
| Spawn may have happened, handle/return missing | Keep PREPARED/DISPATCHED liveness `unknown`; reconcile with the external adapter and exact stable spawn ID; do not spawn again. No heartbeat/timeout is not stop proof; keep the reservation quarantined until typed stop/not-started receipt |

V1 не обещает exactly-once execution и не создаёт distributed transaction framework. Git candidate commit предшествует review; `candidate` completion не означает INTEGRATED (06).

## Takeover, checkout reuse and recovery

Cooperative threat model: lock/epoch защищают helper writes от stale orchestrator, но не останавливают старые processes или прямые filesystem writes. Owner takeover и разрешение product writes — разные решения.

1. Прочитать entry/recover, repository identity, current/prev snapshot; получить lock. Planned transfer использует old owner handoff-ready и resource inventory. Abrupt loss может требовать explicit user attestation, чтобы разрешить owner takeover; attestation/scope сохраняются как authority evidence, но не являются runtime stop evidence. Затем epoch++/new token, control RECOVERING, old attempts fenced, checkout reservations quarantined.
2. Сопоставить attempts/commands с доступными runtime handles/process/session observations. Внешний runtime adapter, а не helper, сообщает exact attempt-bound `stop`/`not_started` через `observe-runtime`; `return_observed` фиксирует return hash, но не liveness stop. Missing UI/handle, timeout, отсутствие heartbeat, epoch change и user attestation не доказывают termination. Receipt must bind runtime instance and declare descendant writers included.
3. **Reuse guard:** только exact typed stop receipt с coverage `descendant_writers=included` либо допустимый `not_started` receipt для попытки без instance/return, плюс свежий checkout audit. `ps`/`lsof`/тишина файлов и user attestations могут быть corroborating/ownership evidence, не machine guard. Если typed receipt отсутствует или coverage unknown/excluded, process liveness remains unknown, reservation stays quarantined, and candidate/review qualification or checkout reuse is blocked.
4. Отчёт называет attempt/checkout и точное недостающее событие/action для runtime adapter. Не создавай duplicate execution при потере handle: exact registration replay returns no-spawn disposition. При невозможности получить stop receipt — сохранить старый target quarantined; отдельный successor scope требует fresh run namespace, accepted scope manifest and `init-successor`, не автоматический duplicate run/worktree в shared common-dir.
5. После reuse guard audit actual tracked/untracked/ignored changes и foreign baseline, reconcile operations и ready inbox. Вернувшийся старый epoch payload — historical evidence; новый owner может принять факты только после нового audit/version checks, не старую authority. Partial product repair выполняет новый worker.
6. Validate docs/evidence/capability fingerprints; invalidate stale gates. Publish recovery result и exact next action на earliest invalid gate, re-ground по 08, затем ACTIVE. Unknown schema → read-only migration diagnostic.

Completion: новый orchestrator продолжает без старого чата/handles при выполненных guard conditions; ambiguous liveness имеет конкретный выход, без timeout-based steal и ложного «epoch убил worker».

## Recovery snapshots and retention

`revision` — номер публикации; workflow checkpoint — durable safe next action; recovery snapshot — отдельная копия ledger, не новая state collection. `ledger.prev.json` хранит предыдущую valid publication. Snapshots создаются на gate и перед dangerous-to-repeat effect; обычный dispatch/return не создаёт ещё одну полную копию. Повторная запись `.git/info/exclude` проверяет наличие exact owned строки и idempotent; для неё не нужен dangerous-effect journal, если граница записи доказанно ограничена этой строкой. Canonical evidence/docs остаются immutable refs.

Default retention: последние 8 **unpinned** recovery snapshots плюс pinned snapshots незавершённых operations/recovery/terminal acceptance. Число — storage policy для E01 measurement, не safety threshold. Referenced evidence/docs/packets и unresolved receipts не удаляются этим retention; run history не зависит от всех intermediate JSON copies. Pruning только exact owned unpinned snapshots после durable publication, никогда при corrupt-state diagnosis. E01 измеряет peak bytes на серии revisions и проверяет восстановление с pinned effects.

## Structural happy path

```text
1 dispatch(T02): route + A02 PREPARED + reservation + packet/binding + stable spawn ID;
  external runtime starts that ID once and publishes start receipt
2 candidate(T02, inbox): ingest DONE + exact worker stop receipt + audit;
  OP9 prepared → Git C → receipt; register RV02 on C; reviewer starts once
3 integrate(T02, review inbox): exact reviewer stop receipt + integrity + PASS on C;
  T02 INTEGRATED, next_action ready work
```

Crash между OP9 и receipt восстанавливается по old HEAD/tree/trailer. C без review остаётся candidate, не dependency fulfillment. Каждый repair создаёт новую attempt и при изменении product новый commit; старый verdict не переносится.
