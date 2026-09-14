# Run ledger and artifacts

**DECISION — OD-01, targeted revision.** JSON хранит structured orchestration state; canonical prose/spec/interfaces остаются Markdown. Один authoritative источник на каждый факт, один orchestrator writer. JSONL replay, executable JS и вручную синхронизируемые status blocks не нужны. [Adjudication](11-review-adjudication.md) объясняет изменения; runtime schema/helper создаются только после E02/E03/E04a.

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

Run ID path-safe и exclusive. Под repository-wide `owner.lock` bootstrap проверяет отсутствие другого nonterminal run. Сначала создаётся owned namespace, затем initial ledger; до публикации product effects не запускаются. Incomplete namespace после сбоя направляется на recovery, не overwrite. Нет mutable current/index.json и альтернативного store после потери control-root. Terminal runs read-only.

`.autopilot` исключён из product commits exact path lists. Bootstrap с имеющейся scope authority добавляет только собственную строку `.autopilot/` в resolved `.git/info/exclude`, сохраняя остальные bytes; runtime permission обрабатывается по 06. При denied exclusion фиксируется ограничение, scoped staging остаётся обязательным. `.gitignore` не редактируется автоматически. Tracked/legacy/foreign `.autopilot` требует namespace/migration решения. Exclude не backup: `git clean -fdx`/`git stash --all` и удаление checkout могут удалить/переместить state. До exclusion `stash -u` также затрагивает untracked state. Report сообщает canonical path и эти конкретные ограничения; remote backup не обещается.

## Schema and authority

Будущая `schemas/contracts.schema.json` — structural SSOT, versioned definitions для ledger/packet/return/review/acceptance. Runtime helper на Python stdlib проверяет только используемый закрытый subset: types, required/unknown fields, enums, refs, arrays/maps и discriminated branches. Неизвестный keyword/schema version → diagnostic без writes; general JSON Schema engine не строится. Dev-time oracle и parity fixtures проверяют subset. Semantic checks: IDs/refs, DAG, gates, owner/epoch, lease, legal transitions и evidence hashes.

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
| `attempts` | ID/kind/mode/subject, packet ref/hash, epoch, state из 01, route ref, exact `checkout`/base/candidate SHA, timestamps/handle observation; embedded `lease` (ID, frozen scope, active/quarantined/released); return ref; repair cause/finding/hypothesis/regression refs; handoff completed/remaining/next action when needed |
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

Successor intake читает final report, approved contracts и decisions последнего релевантного ACCEPTED run по repository identity/явной ссылке. Их refs/hashes становятся prior decisions; current user intent выше. Несовместимое прежнее решение явно superseded. Missing prior artifacts отмечаются unknown; material gap решается targeted read/question, не выдуманной памятью. Экспорт в project docs — отдельный requested deliverable; AGENTS не обновляется.

## Return ingress

Предпочтительный transport при доступной записи — exact attempt inbox в scratch. Agent пишет временный файл, затем атомарно публикует `return.json`; сообщение содержит attempt ID, status и путь, без повторения payload. Это единственное metadata write grant child вне test scratch; canonical docs/ledger/packets/objects остаются orchestrator-owned. Read-only transport возвращает message; runtime file output допустим только при qualified adapter. Полный protocol и validation — [05](05-task-and-return-contracts.md#return-transport-and-ingest).

Helper копирует validated bytes в immutable objects, вычисляет hash и публикует return ref. Scratch никогда не даёт PASS/state authority. Crash после готового файла до ingest не требует нового reviewer, если identity/integrity/stop checks позволяют импорт. Partial/stale inbox сохраняется evidence, не интегрируется. Return file хранится до успешного ingest/recovery; cleanup по 06.

## Atomic publication and intent-level API

Helper — единственный writer ledger; orchestrator вызывает intent commands с owner token/epoch и expected revision. Под fixed OS advisory lock helper rereads state, rejects stale owner/revision, creates immutable referenced payloads, validates entire proposed snapshot/transition, сохраняет valid prior publication в `ledger.prev.json`, пишет same-directory temp, flush/fsync, atomic replace ledger, sync directory. Prior backup failure отменяет новую publication. Lock release после publication. Непривязанные temp/objects после сбоя harmless; generated view failure не rollback.

**Intent-level design target**, имена не frozen CLI API:

| Command | Один model intent / completion |
|---|---|
| `dispatch` | Validate readiness + route, lease/attempt, packet, short brief; persist PREPARED before native spawn |
| `candidate` | Ingest worker return и dispatch handle observation, stop/write audit, prepare candidate Git action; разрешённый commit с receipt, freeze SHA, prepare reviewer packet/attempt в одном intent |
| `integrate` | Ingest review return(s), integrity barrier, issue adjudication refs, current PASS checks; publish INTEGRATED, release lease reservation, next_action |
| `gate` / `amend` / `recover` | Compound subject updates, evidence refs, invalidation и next action; details co-located in respective phase |
| `brief` / `status` | Bounded read projection без full history; brief также возвращается mutation commands |

Helper не вызывает модели, не держит agent loop/daemon и не принимает substantive review decisions. Он может выполнить ограниченную approved Git action внутри intent, **только если это сохраняет native approval boundary**. Иначе возвращает exact effect request для обычного Git tool и принимает receipt; extra round trips измеряются, не скрываются. Durable prepared/applied publications внутри одной команды не одна atomic Git+JSON transaction. Общий unsafe `transact` не agent-facing happy path.

**Happy path bookkeeping target:** ≤4 model-invoked helper calls на routine nonempty ticket от dispatch до INTEGRATED, без repairs/additional axes/environment failure. Целевой путь — 3 calls выше, четвёртый резерв для runtime receipt. Native spawn/wait/Git tool calls считаются отдельно, а internal helper publications не выдаются за zero overhead. E09 измеряет total model turns, helper calls, bytes/tokens, receipts и approvals; transport, требующий больше вызовов, не считается экономически qualified молча. Shared G0–G6/setup counts показываются отдельно и amortized, не теряются в знаменателе.

## Side effects and crash reconciliation

Prepared/applied journal только для commits, init/branch/worktree changes, landing, scoped rollback/cleanup и других действий, опасных при повторе. Pure reads, projections, return ingest — ordinary atomic state. Dispatch — attempt PREPARED до spawn, handle/status observation при следующем intent; потерянный handle не повод повторить spawn. Background writing command должен быть в attempt resource inventory.

| Crash window | Recovery |
|---|---|
| До effect prepared | Effect не должен запускаться; заново решить intent |
| Prepared, actual target unchanged | Проверить authority/expected-before; repeat с тем же operation ID только после reconciliation |
| Effect happened, receipt absent | Commit: operation trailer + old HEAD + intended tree + resulting SHA; worktree: exact path/ref/common-dir/base; init: recorded pre-bootstrap inventory и actual Git identity. Совпало → receipt без повторения |
| Partial effect / foreign drift | uncertain, target quarantine, preserve evidence; exact repair/authority resolution |
| Receipt exists, view stale | Regenerate view, effect не повторять |
| Current JSON corrupt | Validate prev/selected snapshots newest-first; восстановить лишь verified committed publication, reconcile все actual effects после неё |
| Spawn happened, handle/return missing | PREPARED/DISPATCHED с unknown liveness; inventory/inbox/stop reconciliation ниже; no duplicate spawn |

V1 не обещает exactly-once execution и не создаёт distributed transaction framework. Git candidate commit предшествует review; `candidate` completion не означает INTEGRATED (06).

## Takeover, checkout reuse and recovery

Cooperative threat model: lock/epoch защищают helper writes от stale orchestrator, но не останавливают старые processes или прямые filesystem writes. Owner takeover и разрешение product writes — разные решения.

1. Прочитать entry/recover, repository identity, current/prev snapshot; получить lock. Planned transfer использует old owner handoff-ready и resource inventory. Abrupt loss использует runtime-confirmed owner stop либо explicit user attestation, что прежняя сессия закрыта и takeover нужен. Attestation и scope сохраняются evidence; одного возраста ledger недостаточно. Затем epoch++/new token, control RECOVERING, old attempts fenced, leases quarantined.
2. Сопоставить attempts/commands с доступными runtime handles/process/session observations. Подтверждённо живые задачи остановить штатным control и получить completion. Отсутствующий UI/handle не доказательство остановки. E02 квалифицирует fate of children/descendant tools при parent interruption по конкретному build; вывод не переносится между разными failure modes.
3. **Reuse guard:** достаточно runtime-confirmed stop всей writing activity; либо user attestation о завершении старой сессии **и её background writers** плюс доступные corroborating observations без противоречий. Проверить scoped process inventory и два checkout fingerprints через короткое bounded observation window из E02. `ps`/`lsof`/тишина файлов — только corroboration; negative scan с unknown coverage не называется доказательством. При attestation только о закрытом окне запросить точное недостающее подтверждение остановки writers; до него писать product нельзя.
4. Если известный writer остаётся или attestation отсутствует, reuse BLOCKED. Report называет attempt/checkout и действие: stop old runtime/background work, подтвердить остановку, повторить recovery. При невозможности установить это — сохранить старый target quarantined; отдельный successor в новой isolated repository copy возможен лишь как явное новое scope решение, не автоматический duplicate run/worktree в shared common-dir.
5. После reuse guard audit actual tracked/untracked/ignored changes и foreign baseline, reconcile operations и ready inbox. Вернувшийся старый epoch payload — historical evidence; новый owner может принять факты только после нового audit/version checks, не старую authority. Partial product repair выполняет новый worker.
6. Validate docs/evidence/capability fingerprints; invalidate stale gates. Publish recovery result и exact next action на earliest invalid gate, re-ground по 08, затем ACTIVE. Unknown schema → read-only migration diagnostic.

Completion: новый orchestrator продолжает без старого чата/handles при выполненных guard conditions; ambiguous liveness имеет конкретный выход, без timeout-based steal и ложного «epoch убил worker».

## Recovery snapshots and retention

`revision` — номер публикации; workflow checkpoint — durable safe next action; recovery snapshot — отдельная копия ledger, не новая state collection. `ledger.prev.json` хранит предыдущую valid publication. Snapshots создаются на gate и перед dangerous-to-repeat effect; обычный dispatch/return не создаёт ещё одну полную копию. Повторная запись `.git/info/exclude` проверяет наличие exact owned строки и idempotent; для неё не нужен dangerous-effect journal, если граница записи доказанно ограничена этой строкой. Canonical evidence/docs остаются immutable refs.

Default retention: последние 8 **unpinned** recovery snapshots плюс pinned snapshots незавершённых operations/recovery/terminal acceptance. Число — storage policy для E01 measurement, не safety threshold. Referenced evidence/docs/packets и unresolved receipts не удаляются этим retention; run history не зависит от всех intermediate JSON copies. Pruning только exact owned unpinned snapshots после durable publication, никогда при corrupt-state diagnosis. E01 измеряет peak bytes на серии revisions и проверяет восстановление с pinned effects.

## Structural happy path

```text
1 dispatch(T02): route + A02 PREPARED + lease + packet, native spawn follows
2 candidate(T02, inbox): ingest DONE + audit; OP9 prepared → Git C → receipt;
  T02 CANDIDATE/REVIEW, RV02 PREPARED on C, native reviewer follows
3 integrate(T02, review inbox): stopped reviewer + integrity + PASS on C;
  T02 INTEGRATED, next_action ready work
```

Crash между OP9 и receipt восстанавливается по old HEAD/tree/trailer. C без review остаётся candidate, не dependency fulfillment. Каждый repair создаёт новую attempt и при изменении product новый commit; старый verdict не переносится.
