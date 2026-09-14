# Task packets and structured returns

**DECISION — OD-08.** Schema-defined JSON contract с qualified file ingress или message fallback; никакого prose parsing, которое угадывает отсутствующие evidence. Schema ownership — будущий `schemas/contracts.schema.json`; этот документ задаёт semantics. Ни packet, ни return не являются второй authoritative state: [02](02-run-ledger-and-artifacts.md).

## Minimum worker packet

Один outcome, один attempt, одна версия relevant contracts. Всё, что нужно для локального решения, рядом; весь run не вкладывается. Required поля ниже — единственный mandatory payload; platform/tool envelope может передать routing отдельно.

| Field | Минимальное содержимое | Почему нельзя убрать |
|---|---|---|
| `identity` | schema version, `kind=worker`, `mode=implement/repair`, run/ticket/attempt/packet IDs, owner epoch, source revision, relevant contract refs/versions | Проверить stale return и scope до записи |
| `goal` | Один observable outcome | Не заставляет восстанавливать цель из ticket history |
| `acceptance[]` | criterion ID + current expected behavior + relevant requirement wording; immutable version | Criteria inline, чтобы pointer failure не скрыл done condition |
| `workspace` | exact checkout/root, expected base commit, instruction refs/fingerprint | Не писать в wrong worktree и не полагаться на inherited CWD |
| `write` | lease ID, allow entries с operations, deny policy ref + task-specific denies, disposable scratch if used | Все project writes scoped; deny precedence не дублируется текстом |
| `verification[]` | command/scenario, expected outcome, criterion IDs, working directory, evidence required | «Запустить tests» недостаточно |
| `risk` | complexity tier + risk flags + concise reason | Выбирает необходимые остановки и depth проверки |
| `context[]` | Только relevant pointers: path/ref, section/symbol, version/hash и trigger/why-read | Worker читает минимум достаточного контекста |
| `return_target` | Qualified file/message mode; exact inbox path if file, size bound, completion convention | Durable delivery без authority на ledger; semantics ниже |

`context` включает pointer на worker contract/return schema и применимые обязательные instructions. Общие stop conditions и forbidden policy живут в worker contract; пакет не копирует их. Пустая allow zone валидна только для read/no-op task. Absent task-specific denies означает «только общий deny policy», а не unrestricted writes.

### Conditional extensions

| Field | Только когда |
|---|---|
| `dependencies[]` | Есть prerequisites: ticket/contract ID + integrated revision и нужный interface/evidence; отсутствие = нет dependencies |
| `interfaces[]` | Есть consumed/produced seam: contract ref + exact relevant signature/invariant; unrelated interfaces не передаются |
| `environment[]` | Есть дорого полученный либо неочевидный факт, влияющий на execution; дешёвые repo facts не копировать |
| `repair` | Accepted finding IDs, expected/actual, minimal reproduction и regression criterion; previous failed hypothesis только если запрещает бессмысленный повтор |
| `handoff` | Partial candidate fingerprint, completed/remaining criterion IDs, recoverable files и exact next action |
| `authority` | Ticket включает нестандартное protected-path изменение/опасный local action; exact authorized target/effect и decision ref |
| `budget` | Пользователь задал доступный проверяемый лимит; единицы/source/stop condition, не выдуманный token meter |

Relevant contracts всегда присутствуют через identity/context; `interfaces` только ускоряет чтение конкретного seam. Dependencies authoritative в ticket graph и повторяются в packet только как frozen prerequisite slice.

**PROPOSAL / information budget:** обычный packet ориентировочно 600–1,000 слов плюс выбранные file reads; это authoring budget, не runtime truncation threshold. Если большинство полей пусты, это повод убрать optional branches; если mandatory критерии не помещаются, пересмотреть decomposition, не обрезать требования. Маленький ticket обычно существенно короче.

## Dispatch and freshness validation

1. Orchestrator получает ready ticket, фиксирует base/lease/route, генерирует immutable packet и hash.
2. Structural+semantic validation: known IDs, valid current contracts, nonoverlapping zone, integrated dependencies, oracle доступен. Prepared attempt публикуется до spawn.
3. Native child получает packet и applicable instruction pointers. Worker route использует минимальный qualified context; inherited/unknown отмечается DEGRADED_CONTEXT по 03. Review context eligibility строже, G5 требует clean history. Разрешённый runtime syntax берётся из discovery, а не выдумывается.
4. Worker сверяет root/base/criteria до первой записи. Missing context разрешает targeted read; missing contract/zone требует BLOCKED.
5. Return принимается только для matching attempt/packet/contract versions и nonrevoked lease. Late return сохраняется как historical evidence, не получает authority интеграции.

Runtime hard cutoff может не дать return. Orchestrator создаёт LOST/INTERRUPTED observation и вызывает recovery; DONE за worker не придумывается.

## Return transport and ingest

Packet содержит exact `return_target` (attempt inbox либо message mode), size bound и completion convention. File-capable worker/reviewer пишет JSON во временный sibling file, закрывает/flush и atomic-renames в `return.json`; прекращает его менять и завершает writing commands. Короткий message: attempt/status/path. Producer не создаёт ledger record и не объявляет hash доверенным proof.

Ingest по пути принимает только regular non-symlink file в exact granted inbox: resolve path/parent, reject traversal/escape, bounded bytes, read consistent bytes после producer completion, validate schema/attempt/packet hash/epoch/versions/subject. Helper сам хеширует и копирует bytes в immutable objects, затем atomic-publishes ref/status. Worker `files[]` всё равно проверяется independently. Duplicate same hash ingestion idempotent; conflicting payload для attempt → issue, не overwrite. Stale epoch/late return сохраняется history, current owner re-audits actual state до любого использования.

Crash между rename и message/ingest: recovery ищет только зарегистрированные attempt inboxes; matching complete payload импортируется после stop/integrity/version checks без повторного agent run. Temp/partial file не DONE. Если payload утрачен/невалиден, re-request missing data либо fresh inspection; inspection не приписывает старые tests.

Technical read-only reviewer может вернуть structured message; runtime `output-last-message` file — отдельный E03-qualified способ с тем же ingest contract. Message bytes сохраняются без model paraphrase, если tool transport это позволяет; иначе точный повтор учитывается в E09, не обещается zero duplication. File path сам по себе не receipt или review PASS.

## Worker return: base fields

JSON object без conversational history. Обязательны:

| Field | Contract |
|---|---|
| `identity` | attempt/packet ID, packet hash, contract refs seen |
| `status` | `DONE | BLOCKED | FAILED | HANDOFF` |
| `result` | Одно короткое наблюдаемое изменение/причина остановки |
| `files[]` | repo-relative path + operation (`create/modify/delete/rename`); rename содержит from/to; no-op = [] |
| `checks[]` | check ID/scenario, outcome `pass/fail/not_run/unverifiable`, actual, evidence ref; command + exit code when run; not_run reason обязателен |
| `criteria[]` | criterion ID → `satisfied/unsatisfied/unverifiable` + evidence refs; не claim о run acceptance |

Conditional:

- `issues[]`: type/cause, affected refs, expected/actual evidence, required change/authority; обязателен для BLOCKED/FAILED и material concerns.
- `interface_delta[]`: planned conformance при значимом public seam или proposed amendment при обнаруженном gap; никакого «already changed contract» без authority.
- `handoff`: safe partial fingerprint, completed/remaining, pending commands/resources; обязателен для HANDOFF.
- `finding_resolution[]`: finding ID → regression evidence; обязателен для repair mode.

`next_action` worker не обязательное поле: orchestrator выводит маршрут из status/cause. Независимая actual write-set verification всегда сравнивает `files` с filesystem/Git.

### Legacy fields decision

| Old field | V1 |
|---|---|
| STATUS | Keep: `status` |
| FILES | Keep: `files`, независимо проверяется |
| TESTS | Modify: `checks` охватывает tests/live/manual/edge и not-run |
| INTERFACES | Conditional `interface_delta`; default отсутствие = изменений контракта не заявлено, аудит всё равно проверяет |
| REQUIREMENTS | Replace: `criteria` с точным oracle evidence; requirement aggregate derived |
| CONCERNS / BLOCKERS | Merge: typed `issues`, distinction impact `advisory/blocking` и cause |
| COMMIT | Drop from worker return: worker не commit. Commit receipt принадлежит orchestrator operation |

### Status semantics

DONE: все packet criteria локально satisfied, required checks pass, нет blocking issues. No-op DONE допустим с evidence существующего поведения. Missing required live check → BLOCKED/unverifiable, а не DONE «в пределах среды».

BLOCKED: дальнейший шаг требует contract/dependency/zone/environment/permission/user resolution; includes partial files/checks. FAILED: выполненный подход опровергнут evidence; cause может быть unknown. HANDOFF: остановка контекста при сохранённом partial state, без ложной completion.

Issue `cause`: `implementation | contract | oracle | environment | permission | ownership | orchestration | user_intent | unknown`. Дополнительно `failure_signature` — стабильное смысловое expected/actual discrepancy для detection повторов; не хеш raw лога.

### Три обязательных сообщения о проблемах

```text
CONTRACT: expected relation conflicts between IC2/v3 and AC7;
  evidence refs; requested clarification; no new contract applied.
ENVIRONMENT: verification command cannot start, tool/version/error;
  criteria not checked; partial state; capability fact to invalidate.
OWNERSHIP: required path outside L04;
  exact path and reason; no write made there; proposed zone amendment.
```

Эти строки иллюстрируют содержание typed issues, не вводят второй prose return protocol.

## Reviewer/research input packet

Required reviewer envelope: identity (run/attempt/packet IDs, schema, source revision), `kind=review`, mandate, subject fingerprint + frozen view location, current criterion/contract slice, assigned axes/questions, permitted read/scratch resources + isolation fact ref, verification opportunities/constraints, return schema pointer и `return_target` по transport contract. Change review дополнительно получает diff base/candidate, coverage review — proposed spec vs current intent, plan review — DAG/zones/interfaces. Shared contracts не включают author/worker self-rating. Expected outcomes передаются; prior implementation test results не задают initial verdict.

Research branch: `kind=research`, identity, один decision-relevant question, scope/source authority, permitted read/probe resources, context pointers, completion/return contract. Criteria/diff поля product review для него отсутствуют. Выход facts не даёт права менять contract без orchestrator decision.

Applicable safety/project instructions сохраняют приоритет: clean-session setup обязан выполнить применимые ограничения, а instruction, требующий implementation history, делает этот context неeligible для blind mandate; такую несовместимость записывают как blocker, не обходят удалением правила.

Final acceptance заменяет generic contract slice строго ограниченной projection ниже. Это discriminated branch той же role schema, не второй формат с произвольными полями. Любой review packet привязан к immutable subject, поэтому verdict нельзя перенести на изменившийся код/intent.

## Review return

Required envelope: identity, `subject_fingerprint`, `verdict PASS/BLOCK/UNVERIFIABLE`, `coverage[]`, `checks[]`, `findings[]`. Пустые findings допустимы только с coverage фактически проверенных criteria/scopes. Reviewer не получает worker self-report/test pass claims до initial verdict; known commands и независимые expected outcomes можно передавать.

Finding fields: local ID (orchestrator присваивает global ID), axis, impact `blocking/advisory`, claim, expected/actual, source location/scenario evidence, affected criterion/contract refs, optional cause hypothesis marked INFERENCE. Review PASS относится к exact subject и mandate, не ко всему продукту.

Research return — тот же read-only envelope, discriminated kind `research`: question, `CONFIRMED/CONTRADICTED/UNRESOLVED`, facts with provenance, inference/uncertainty, decision impact. Объединение roles не заставляет research выдавать ложный code-review PASS.

## Final independent verifier: current intent without implementation narrative

**DECISION.** Acceptance package — отдельная deterministic allowlist projection из approved current intent, а не старый brief и не полный ledger. Она содержит:

1. Current goal, exact requirement wording/IDs, approved amendments с продуктовым before/after и user authority provenance. Технические repair reasons из amendments отфильтрованы.
2. Все active observable criteria, exclusions и явно approved deferred/dropped items, не скрытые за процентом completion.
3. Candidate identity и runnable product snapshot/endpoint, benign launch/setup facts, allowed test resources и environment constraints. Credentials не копируются.
4. Acceptance return schema и mandate: оценить criterion outcome собственными observable checks, сообщить missing/unverifiable.

Она не содержит spec/plan/tickets, worker returns, tests-pass summary, review log, repaired defect IDs, commit messages/history, repair narrative или предыдущий acceptance verdict. Source files и shipped product docs доступны как продукт; внутренние `.autopilot`, `.git` history и скрытые orchestration artifacts отсутствуют в exported review view. Verifier может исследовать shipped tests как код, но их assertions не подменяют user intent oracle.

Projection validation до spawn: exact current intent revision; каждый active criterion присутствует один раз; только approved amendments; no hidden status fields/self-ratings; candidate SHA matches pristine export; дополнительные manifests относятся к audit/fixtures, не альтернативной candidate identity. Orchestrator не пишет новый «красивый brief» вручную. Human-readable acceptance projection вне обычных views создаётся в disposable review scratch и hash регистрируется в ledger.

**Independence grades:** packet/history isolation — required; недоступность истории в exported view — required; authoritative integrity/transport qualification — 06/07. Это методическая независимость, не blind secrecy against malicious agent с broad filesystem reads. Если native child унаследовал implementation history, он не eligible; нужен independent clean process/session. Для automatic route действует strict E03 standard; manual route ниже допускает operator-attested clean setup, сохраняя незагрязнённый packet и техническое отделение authoritative resources (06). Candidate snapshot alone не исправляет inherited bias.

Final return: `intent_revision`, `candidate_fingerprint`, `outcomes[]` для каждого active criterion (`fulfilled/partial/missing/unverifiable`), checks/evidence, findings, verdict. PASS iff все active outcomes fulfilled и нет blocking finding. Approved exclusion отдельно listed, не PASS. Unverifiable active criterion блокирует G5; user может изменить intent через amendment, после чего создаётся новая projection и новый verifier round. Он не может «подписать зелёный» исходный непроверенный criterion.

Все accepted findings одного G5 раунда adjudicate и исправить одной repair wave с dependency ordering. Targeted re-reviews закрывают её findings; затем один fresh G5 на общем новом candidate. Каждый product repair инвалидирует старый verdict, но не требует отдельного полного G5 до завершения wave. Contract/intent amendment проходит соответствующие gates до новой projection; незакрытый blocker нельзя скрыть batching.

## User-assisted critical/G5 handoff

**DECISION — 2026-09-13, D-21, targeted policy revision.** Пока automatic strict transport не qualified, V1 штатно поддерживает ручную доставку пакета независимому reviewer в новую clean session с declared review-surface/input boundary. Пользователь обеспечивает setup/transfer, reviewer выполняет проверку, orchestrator валидирует evidence и gate. Это не user approval вместо G5 и не self-review основного агента. Manual route не обещает недоступность unobservable underlying host; safety boundary — только переданные/наблюдаемые project inputs и правила их использования, см. [06](06-safety-write-git-model.md#manual-review-environment).

1. На G0 сообщить automation boundary; до affected critical work/G3 подтвердить доступность выбранного fallback и oracle. Выбор этого V1 режима включает будущие handoffs, не требует повторного согласования самого режима на каждом раунде. Если user требует fully automatic acceptance, назвать отсутствующий strict transport как capability blocker. Routine tickets продолжают прежний automatic path.
2. Orchestrator готовит reviewable handoff: immutable subject (candidate SHA/tree для change/G5; hashes current document versions для G2/G3), export bytes/hash/manifest, packet ID/hash и mandate, criteria, applicable instructions, benign setup/resources, return schema и короткий operator checklist. G5 получает только existing current-intent allowlist projection; critical axis — свой relevant contract/risk slice. Extra envelope не добавляет narratives/worker test claims. Никаких ссылок для reviewer на authoritative paths, ledger, credentials или Git history. Export missing live dependencies → UNVERIFIABLE, не усечённый scope.
3. Пользователь запускает независимую **новую** reviewer session: без fork/resume author/worker thread, project-memory/chat import или inherited implementation narrative. Фиксируются session/launch provenance (если наблюдаемы), hash переданного packet/export и operator attestation о чистом вводе/отсутствии иных project inputs. Достаточны metadata/краткий setup receipt; hidden prompts и unobservable host properties не добываются. `MANUAL_ATTESTED_CLEAN` означает явно принятую human trust boundary по входам и контексту, не доказанную runtime strict freshness или OS isolation. Известная contamination, authoritative input access или connector use делает session ineligible независимо от attestation. Critical axis остаётся отдельным reviewer mandate от combined review; G5 каждого нового candidate round — новый clean context без предыдущего verdict.
4. До product checks принять environment receipt по 06. Пользователь переносит **только** подготовленный bundle и затем exact structured return/check artifacts. Receipt описывает observable review surface, input inventory/hashes, effective grants и known tool connections; она не должна утверждать недоступность непроверяемого host-layer. Known authoritative input access, connector use или credential use остаются blocker. External provider, upload или новый cost scope требуют existing/explicit authority на выбранное место назначения; skill не отправляет сообщения/данные сам. Другой provider не обязателен: отдельная Codex session подходит при выполненных условиях.
5. Ожидание использует существующий control BLOCKED (`manual_review_pending`) в VERIFY для G5 либо в affected phase для critical axis. До handoff — PREPARED attempt; подтверждение запуска → DISPATCHED observation; payload → RETURNED после validation. Новых phase/control/record collections нет. Durable next_action содержит packet/export refs, ожидаемый receipt и способ продолжить. Native processes остановлены по 02; отдельная reviewer session работает только со своей copy. Repository lock не удерживается на время человеческого ожидания.
6. Import — existing file/message ingest: exact bytes, matching attempt/packet/subject/intent, setup receipt, every required criterion/axis и independent checks. Orchestrator сохраняет source provenance, выполняет authoritative integrity check, adjudicates issues; missing/truncated/mismatched evidence → BLOCKED/re-request, не заполнение PASS. Operator «я согласен» без reviewer evidence G5 не закрывает. Manual return не исполняется как script и не вносит reviewer fixes в product.
7. Interruption/resume использует 02 и 08: читать pending handoff, сверить actual candidate/intent и receipt, не переотправлять bundle/не запускать reviewer повторно вслепую. Legitimate owner/status publications сверяются по committed revisions; чужой drift или changed candidate/intent инвалидирует result. Lost output можно запросить повторно для того же subject; новый G5 round получает fresh packet/context. Accepted findings → прежняя repair wave → один новый handoff/G5; критические re-reviews повторяют required axis, не откладываются до G5 ради экономии.

Final report называет `acceptance_transport=user_assisted`, context/setup evidence grade, reviewer provenance, round/intervention counts и limitations. Automatic gate bookkeeping после валидного manual return допустимо; поле `acceptance_policy=automatic` по-прежнему означает отсутствие дополнительного G6 human sign-off, а не отсутствие user-assisted transport. Human acceptance, если отдельно requested, остаётся отдельным условием G6.

**Completion:** independent per-criterion PASS на неизменном candidate/current intent плюс валидные input-boundary/context/integrity receipts. Known exposure of authoritative inputs, contaminated context, missing live oracle или missing receipt оставляет конкретный run BLOCKED; отсутствие доказательства unobservable host-level isolation само по себе не блокирует manual fallback и не присваивает `STRICT_FRESH`.

## Malformed returns and context transfer

Structural error → re-request недостающие поля без повторного исполнения. Если thread потерян, fresh read-only inspection подтверждает состояние с собственным evidence; missing tests остаются not_run. Orchestrator не заполняет PASS, files или commit по догадке.

Следующий worker получает current contracts, integrated dependency slice и применимые facts. Failed attempts пересказываются лишь как `hypothesis / observation / constraint`, если нужны для выбора нового подхода. Diff/logs передаются точечными pointers. Пересылка полной history, автоматическое чтение всех tickets или возврат raw worker conversations не являются fallback.

**Completion:** свежий worker может определить goal, permitted effects, done condition и stop condition из packet+conditional reads; return достаточен для triage, но не позволяет обойти independent verification.
