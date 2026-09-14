# Decisions, conflicts and experiments

**DECISION — updated 2026-09-13 (D-21).** Реестр закрывает все OD из [research/08-open-decisions.md](../research/08-open-decisions.md). Статус решения и статус его runtime validation различаются. DECIDED не значит runtime-tested; EXPERIMENT REQUIRED не даёт права обходить выбранный safe default.

Статусы: **DECIDED**, **CONSERVATIVE DEFAULT**, **RUNTIME DISCOVERY**, **EXPERIMENT REQUIRED**, **USER DECISION REQUIRED**. Открытых архитектурных вопросов без disposition/точного действия нет. Текущий запрос разрешает только design revision. E02/E04a и routine E03 дали usable evidence; D-21 снимает package implementation blocker через explicit manual critical/G5 contract. Strict automatic E03 остаётся FAIL/UNKNOWN. Material authority будущего run не предрешена.

## OD disposition matrix

| OD | Status and decision | Rationale / trade-off | Owner and residual validation |
|---|---|---|---|
| OD-01 ledger format | **DECIDED:** JSON orchestration state + canonical Markdown refs/hashes, atomic single writer, selective recovery snapshots; no JSONL replay/JS | Один local run; меньше concurrent/replay state. Ledger локален, не remote disaster backup | 02; E01 release-blocking |
| OD-02 model/effort discovery | **RUNTIME DISCOVERY:** exposed native options → accepted binding → adequate inherited route; no guessed catalog/slug | Docs/API names не account availability. Full cost optimization unavailable без метрик | 04/07; E02 qualification, E05 tuning |
| OD-03 retry/repair/escalation | **CONSERVATIVE DEFAULT:** cause-first; safe transient retry; local stable repair may retain context; repeated causal defect requires diagnostic/fresh; no repeat without changed evidence/hypothesis | Сохраняет прогресс без arbitrary «2 repairs then fail». Optimal numeric thresholds неизвестны | 04; E05 functional guard required, economics optional |
| OD-04 Astra/external | **DECIDED:** frontier optional escalation при unresolved critical uncertainty; external only explicitly requested handoff, no mandatory provider | Independence/oracle важнее имени; отсутствие Astra не блокирует ядро | 04; E06 comparative tuning, external authority runtime-only |
| OD-05 review topology | **CONSERVATIVE DEFAULT:** one combined reviewer routine; risk mandate elevated; independent additional axis critical; final always fresh | Это достаточный проверяемый defense-in-depth default, не доказанный optimal count | 03/04/05; E06 functional review coverage before release; comparative savings optional |
| OD-06 reviewer/write enforcement | **DECIDED:** immutable subject + disposable review copy + independent integrity barrier; critical transient-risk axes need technical restriction | Detection при cooperative model допустима после qualification; post-check не обнаруживает write-and-restore | 05/06/07; routine E03 qualified; critical/G5 user-assisted D-21, E03-M до release; automatic strict upgrade post-V1 |
| OD-07 Git/worktrees | **DECIDED:** serial writer, run branch, orchestrator candidate commit before review; INTEGRATED after PASS; qualified sibling worktree for dirty/busy checkout; E10 parallel extension | Idea Scout isolation cleanup evidence учтён без переноса hybrid-specific mechanics. Меньше parallel speed, меньше merge complexity | 06; E04a PASS clean path/conditional placement; E04b recovery before release; clean checkout default |
| OD-08 context/return | **DECIDED:** minimal JSON packet/return, file inbox preferred with message fallback; worker context degradation allowed, independent review context graded, strict G5 | Native summary не structural guarantee; new handle не context isolation | 03/05/07; E02 scoped PASS with UNKNOWN arms; manual G5 context D-21; E08 correctness before release |
| OD-09 depth/modes | **DECIDED:** complexity + consequence risk; compact ≤2 routine tickets with combined artifact/assessment and distinct gates; no T0–T3 quotas | Один scalar tier смешивал scope, correctness и стоимость. User override не отменяет safety | 04/09; E05 later classification tuning |
| OD-10 project memory edits | **DECIDED:** no automatic AGENTS/CLAUDE/config/ADR edits; successor reads prior ACCEPTED report/contracts/decisions | Brief preserve-by-default и actual resume evidence; read-only continuity сохраняется без project instruction writes | 06/08/09; future explicit deliverable, no present user blocker |
| OD-11 Git-only | **DECIDED:** V1 Git-required before dispatch; existing baseline or scoped greenfield init/initial commit in G0 | Реальный software use case и checkpoint evidence оправдывают отказ от второй no-Git safety системы; greenfield использует тот же Git protocol | 06/07; E04a bootstrap/approval PASS scoped, E04b crash recovery pending |
| OD-12 support floor | **DECIDED:** macOS local CLI primary qualification; local app/IDE admitted by relevant probes; tested builds with provenance | Narrow qualification avoids universal surface adapters; OS/cloud portability deferred, surface label alone not a gate | 07/09; E02–E04 populate exact builds at release |

## Additional decisions needed for a complete contract

| ID | Status / decision | Why |
|---|---|---|
| D-13 | **DECIDED:** three roles; research/final reviewer mandates, repair worker mode | Не создавать агента на каждую фазу |
| D-14 | **DECIDED:** final verifier gets deterministic current-intent projection + approved amendments + observable criteria | Blind к implementation narrative, но не слеп к новой воле пользователя |
| D-15 | **DECIDED:** one active run at canonical primary checkout, single ledger owner epoch; canonical prose hash-referenced, status/report derived | Устраняет competing state после смены worktree/thread |
| D-16 | **DECIDED:** no-subagents blocks product execution; planning/recovery/status still useful | Parent fallback нарушает role boundary; worker freshness не приравнивается к G5 independence |
| D-17 | **DECIDED:** explicit invocation via Codex metadata, 16 core future files; optional reviewer setup artifact after E03 | Writing-for-agents mechanics adapted to actual Codex syntax |
| D-18 | **DECIDED:** ACCEPTED refers to exact local run candidate, not implicit push/deploy/default-branch merge | Reviewable completion без расширения external authority |
| D-19 | **DECIDED:** stdlib intent-level helper, selective effect journal, ≤4 bookkeeping calls/ticket target, not autonomous daemon | Atomic publication/schema/write audit require code; orchestration remains native agent behavior |
| D-20 | **DECIDED:** per-criterion UNVERIFIABLE blocks G5 while criterion active | Невозможность проверки нельзя маскировать общим PASS; authorized amendment сохраняет original history |
| D-21 | **DECIDED:** V1 user-assisted critical/G5 in isolated export environment; operator-attested clean input, independent structured outcome, validated import (05/06) | E03 не qualified automatic strict route; ограниченно принимаем human setup trust вместо runtime freshness proof. Candidate/intent/axis/technical boundary сохраняются; manual roundtrip E03-M ещё NOT RUN |

## Source conflicts and evidence limits

| Conflict | FACT / OBSERVED | Resolution |
|---|---|---|
| Brief valuable `.autopilot/state.js` vs audit validated data proposal | **OBSERVED:** state semantics помогли resume; необходимость JS/dashboard не доказана | Сохраняем данные, заменяем формат по OD-01; ссылки 02/08 |
| Research no-subagents fallback vs brief orchestration boundary | **FACT:** audit — proposals, brief выше по приоритету | D-16: no-native-worker execution blocked, не parent self-implementation; unknown worker freshness may degrade |
| writing-for-agents invocation syntax vs Codex | **FACT:** установленный SKILL-MECHANICS описывает `disable-model-invocation`; current [Build skills](https://learn.chatgpt.com/docs/build-skills) указывает `allow_implicit_invocation` в metadata | Методология сохраняется, syntax Codex-native; zero metadata context не обещается |
| Model alias/effort vocab в official sources | **FACT:** audit [source register](../references/official/openai-links.md) фиксирует `minimal/none/max/ultra` и aliases; [Models](https://learn.chatgpt.com/docs/models) описывает Ultra как multi-agent mode | Runtime resolver не использует enum из чужого surface или API availability; OD-02 |
| Custom reviewer defaults vs inherited live overrides | **FACT:** [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents) описывает live parent overrides | Technical isolation qualified, .toml label не proof |
| Worktree independence vs shared metadata/lifecycle | **OBSERVED:** Idea Scout suffered early cleanup; **FACT:** [Worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees) различает managed/permanent, shared Git metadata и optional ignored-file inclusion | Permanent explicit run worktree; no automatic secret copy; cleanup belongs to orchestrator, not handle lifetime |
| Always two persistent reviewers / hard repair caps vs empirical V1 | **OBSERVED:** audit фиксирует recreated reviewers, 37 repairs/7 handoffs и varying counts | Role mandate durable, process disposable; cause/progress rules вместо механических counters |
| Initial brief-only final vs evolving intent | **FACT:** user explicitly requires current intent + approved amendments | D-14 deterministic projection исключает history, не новые требования |

Исходный design фиксировал official checks 2026-09-12. В targeted revision повторно открыты [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents), [Non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode) и [Agent approvals/security](https://learn.chatgpt.com/docs/agent-approvals-security). Structured output/file delivery и read-only настройки документированы, их nested/session behavior остаётся E02/E03. Audit references не изменялись. Документация подтверждает primitives, не runtime qualification в аккаунте пользователя. Источник, не доказывающий fresh-context transport details, не закрывает E02.

## E03 blocker adaptation — 2026-09-13

[Qualification summary](../experiments/SUMMARY.md) остаётся историческим verdict по прежнему scope: E02/E04a usable, E03 strict route absent. Native child смог писать authoritative sentinels; `codex exec` сначала отказал на outer environment initialization, затем approved process получил 401 и не выполнил reviewer turn ([raw](../experiments/raw/e03-codex-exec-results.md)). Поэтому login/новый CWD, custom file или слово read-only не дают нового PASS.

**Decision D-21:** реализовать V1 с automatic workers/routine review/Git и user-assisted critical/G5. Minimal alternatives и environment boundary — 06; полный handoff/return/recovery contract — 05. Мы переносим запуск/доставку strict review к пользователю и явно допускаем `MANUAL_ATTESTED_CLEAN` setup provenance. Не переносим author narrative в G5, не принимаем reviewer fixes, не убираем critical axis или live criteria. Независимый ответ остаётся необходимым условием ACCEPTED.

Отдельный export сам по себе уже испытан и недостаточен для strict защиты. Отдельная среда без authoritative repo/tool access — допустимый technical boundary; наличие такой среды у пользователя ещё не измерено. Manual contract implementable через существующие artifacts/attempts/capabilities/evidence, без новых ledger collections, lifecycle states, workers или Git mechanisms. **Implementation readiness относится к этому contract; release readiness требует actual E03-M roundtrip.** Если среда не обеспечена, affected run BLOCKED. Fully automatic V1 по текущему evidence не обещается.

Official checks 2026-09-13: [Non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode) описывает read-only/structured output и `--ephemeral` как отсутствие persisted session rollouts; [Developer commands](https://learn.chatgpt.com/docs/developer-commands) различает fresh chat и fork. Эти primitives не подтверждают отсутствие memory/config/tool access для E03 account. Автоматическое исполнение этих вариантов отложено до targeted qualification, не реализуется здесь.

## Experiments: bounded test and decision rule

E02/E03/E04a **выполнены отдельным qualification pass**; факты и raw logs — [experiments/SUMMARY](../experiments/SUMMARY.md). Этот adaptation pass их не повторял и reports не менял. Остальные E01/E04b/E05–E10 и новый manual validation E03-M NOT RUN. Порядок теперь: completed spikes → D-21 disposition → separately authorized schema/helper + E01/E04b/manual handoff implementation → E03-M, functional E05/E06, E07/E08/E09. E10 и automatic strict transport upgrades post-V1.

### E01 — Ledger publication, fencing and interruption

**EXPERIMENT REQUIRED — release blocker.** Owner: implementation helper/test harness.

Минимум: один run, один ticket, два конкурирующих orchestrator tokens. Проверить planned/attested takeover отдельно от reuse, old-epoch return ingestion, corrupt prev, Markdown drift/version publication, lazy views, bounded snapshot retention с pinned effects и series из сотен revisions. Прервать update до temporary write, после fsync до replace, после replace до views; отдельно corrupt current JSON и дать valid previous checkpoint. Попробовать stale revision/epoch transaction. Simulate prepared effect with/without observed Git receipt.

PASS: один committed authoritative revision; stale owner не пишет; невыбранный tmp не authority; views regenerate; unknown effect не повторяется; recovery next_action определён без chat. FAIL: execution disabled до исправления helper; Markdown/manual editing не fallback. Измерять peak/retained bytes, publications/model helper calls и recovery operations для evidence, без заранее выдуманного latency target.

### E02 — Native context, freshness and parent interruption

**OBSERVED: PASS для bounded worker prerequisites, UNKNOWN/FAIL arms сохранены** — [E02 report](../experiments/E02-native-context-and-interruption.md). Ниже исходный test contract для targeted recheck, не требование повторить весь experiment. Disposable packet/fixture, без runtime schema/helper. Каждый tested build имеет separate outcomes worker-context, independent-review-context, strict-final-context, parent/child liveness, return transport и route adequacy.

Parent содержит synthetic history marker, packet — другой marker и applicable instruction pointer. Проверить minimal-context launch по actual tool schema, доступное input evidence, behavioural non-recall и **positive control** через заведомо inherited channel. Failed positive control → test inconclusive. Known worker inheritance/UNKNOWN не запрещает bounded execution: DEGRADED_CONTEXT с measured bytes/anchoring limitation. Для coverage/plan/change operational behavioural clean PASS допустим, known author narrative contamination — FAIL этого review route. Для G5 нужны inspectable input/runtime contract или official guarantee плюс smoke; non-recall alone остаётся UNKNOWN.

На fixture создать child с bounded writing command и durable attempt marker, затем прервать parent: normal stop, abrupt process/session loss и loss of UI connection проверяются отдельно. Наблюдать судьбу child/descendant tools, partial files, available control handles и stop evidence. Имитировать crash после spawn до handle publication. PASS recovery design: известны evidence source и точные takeover/reuse paths по 02, включая attestation если runtime не даёт proof; silent checkout/timeout не принимается за termination guarantee. Не утверждать parent-kill semantics по одному disconnect. Synthetic known-live writer обязан оставаться quarantined.

Return spike: complete file → kill parent before message/ingest, partial temp, message-only, duplicate/stale payload; показать восстановление completed return без нового agent run, когда возможно. Проверить cancelled child и rejected model/effort без duplicate spawn. Requested и observed model/effort различать; проверить opaque child с known inheritance chain и с custom/default uncertainty. Actual identity UNKNOWN допускает independent adequacy proof, не guessed model.

**Exit artifact:** exact build provenance/tool schema/context mode, evidence grades и limitations, stop/attestation protocol observations, delivery overhead. Viable native worker route обязателен; отсутствие strict native final route передаётся E03 для clean process/session arm, не ослабляет G5. Нет viable worker route → implementation blocked; не parent writes.

### E03 — Reviewer isolation and transports

**OBSERVED: FAIL / BLOCKED по исходному strict qualification contract** — [E03 report](../experiments/E03-reviewer-isolation-and-transports.md). Routine native detection arm PASS; automatic strict critical/G5 не qualified. D-21 меняет V1 delivery boundary, а не результаты experiment. Ниже исходная matrix для eventual automatic requalification. Handwritten packets, frozen Git candidate + canonical-state sentinel, disposable copy и mutation-test fixture. Ниже arms — сравнение, а не выбранные dependencies.

| Arm | Что подтвердить |
|---|---|
| Native reviewer + SHA export + integrity barrier | Persistent candidate/state/foreign-file tampering обнаруживается независимо; normal caches/source mutation в copy допустимы; pristine checks остаются bound to SHA |
| Custom read-only reviewer agent | Один scoped setup file, current official supported location/config; effective policy без override и с live parent override; baseline hashes и file/message return. Existing instructions/config preserve |
| `codex exec` read-only + structured output | Clean process input без parent history; actual sandbox, nested macOS Seatbelt, network/auth/approval behavior и scope output file; `--output-schema`/file-output support по actual CLI. Только bounded reviewer, не worker bridge/daemon |
| Native `/review` | Frozen scope, independent context, structured return или validated delivery; не presumed G5 equivalent |
| Other official mechanism / optional hooks | Добавить только с direct official reference и exposed runtime capability. Hook может усилить detection/control при setup authority; не mandatory config system |
| Manual clean session | Исходный arm не выполнялся; D-21 делает его supported critical/G5 fallback contract, отдельная validation E03-M ниже; routine review остаётся automatic |

Для automatic arms проверить default permission и live override, candidate SHA/ledger/docs/index tamper, hash check до ingestion, interrupted reviewer/process, mutation followed by restore в copy и pristine rerun. Размещение copy вне source tree с разрешёнными scratch roots проверяется отдельно от sibling worktree E04a. Отдельный write-and-restore к authoritative sentinel демонстрирует предел post-hoc detection: он **не** получает prevention PASS. Critical axis с transient-impact threat допускается лишь при technical restriction authoritative roots/tools. Test outputs в disposable scratch разрешены и не считаются product repair.

Исходный E03 PASS criterion (полностью не достигнут) — хотя бы один automatic qualified route для routine coverage/plan/change с independent context и integrity invariant; для required critical axes есть restriction; для G5 strict clean context + export без history + integrity, automated preferred/manual last resort reported. Градации context и protection записываются отдельно, overall PASS не прячет failed arm. При broad-write detection current ledger/target frozen на barrier; E09 измеряет цену сериализации. Export проверяется против Git tree (attributes/missing files), а не только собственной manifest. No tests on reviewer-mutated product counted as pristine PASS.

**Exit artifact:** selected transport by mandate/risk, setup authority/permission requirements, return ingress, context/stop evidence, automatic/manual boundaries и failed arms. Если отсутствует viable ordinary independent review, qualification не complete. Решение обновляет 03/05/06/07/08/10 без изменения lifecycle/roles.

### E03-M — User-assisted critical/G5 validation before release

**BLOCKED under prior D-21 wording — release blocker для assisted mode, не новый pre-implementation transport spike.** Минимум один реальный handoff в user-prepared scoped review surface с independent fresh session, input/context receipts и actual structured result. Можно выполнить handcrafted до helper; integrated import/resume затем повторяется на implementation. «Пользователь может открыть чат» не evidence PASS.

Fixture: frozen green-but-broken candidate + current-intent projection; отдельный critical-axis packet без leakage между mandates. Operator передаёт только bundle, проверяет hash и confirms clean context; observable review-surface topology/inventory и nonsecret input-boundary probes по 06 recorded. Host-level isolation и отсутствие непроверяемых system env vars не требуются как доказательство; known authoritative input/connector access остаётся blocker. Reviewer делает observable checks, ловит seeded defect; repair выполняет worker, новый candidate → новый clean G5 с per-criterion PASS. G5 никогда не получает previous verdict/repair narrative.

Проверить pause/resume между prepared handoff, launch receipt и ingest; completed return не теряется/не требует duplicate review, old owner/changed intent/candidate не получают stale PASS. Required negative cases: missing input/context receipt, same author thread/fork, known connector к authoritative state, tampered export, plain user sign-off и unavailable oracle → BLOCKED/UNVERIFIABLE. Неизвестные unobservable host-layer свойства фиксируются как residual trust; automatic E03 не переименовывается в PASS.

PASS фиксирует tested manual destination/review-surface topology, observed checks, user attestations отдельно от inference, exact bundle/candidate/intent, return provenance, user interventions/time и residual host/context trust. E07/E08/E09 используют этот qualified manual workflow. Полное устранение участия пользователя или получение strict OS-level isolation — отдельная post-V1 restricted E03 qualification.

### E04 — Git approvals, worktree placement and recovery

**SPLIT QUALIFICATION:** E04a PASS для clean Git path, conditional worktree/UNKNOWN arms — [report](../experiments/E04a-git-approvals-bootstrap-worktrees.md); E04b NOT RUN. Ниже сохранены test contracts.

**E04a — до schema/helper.** Minimal disposable clean repo и empty/seed folder. Под actual default permission/approval mode выполнить scoped init/initial commit, branch, candidate commit **до review**, repair commit, local exclude и optional permanent sibling worktree. Записать каждое approval request/automatic review/prompt/denial, effective reusable-prefix behavior и tool boundary. Не считать prefix blanket sandbox permission. Проверить partial denial без alternate-tool bypass; missing Git identity/hooks должны иметь exact blocker.

Для worktree проверить отдельно execution-root writes и shared `.git` writes, placement outside primary tree, session с разрешённым sibling root и без него, source scanning/ignored fixtures, life после session loss. Вложенный checkout не fallback. Missing sibling permission → qualified clean exclusive checkout либо exact setup action, не dirty writes. Greenfield seed inventory сохраняется, unknown existing folder требует scope decision, secrets не попадают в baseline.

PASS E04a: viable authorized clean Git flow и known approval cost; worktree может остаться disabled с clean-only fallback. Если required Git actions невозможны, schema/helper implementation blocked для target. **Exit artifact:** selected clean/worktree mode, exact command/effect/approval strategy, roots/common-dir, bootstrap rules, counts/limitations.

**E04b — после helper, до release.** Добавить dirty tracked/untracked foreign files, ignored output, symlink и harmless hook fixture. Audit exact paths, candidate commit/tree, pristine review/export и integrity; interrupt после commit до receipt и во время partial worker. Reconcile один receipt по operation/base/tree без repeat; cancel/resume по attestation/stop guard не удаляет foreign work. Проверить `clean -fd`, `clean -fdx`, `stash -u`, `stash --all` **только на disposable state fixtures**, подтвердить exclude/report limitations. Unexpected hook mutation даёт new audit/review, не silently accepted SHA.

PASS E04b: foreign hashes preserved, actual tracked/untracked/ignored/type/rename audit catches violations, wrong roots block, worktree persists if enabled, duplicate effects не возникают, permissions не обходятся. Original project never test target.

### E05 — Cause routing and economic tuning

**CONSERVATIVE DEFAULT + EXPERIMENT REQUIRED (tuning).** Functional routing guard обязателен до release; model optimality нет.

Минимум functional: labelled fixtures для local omission, повторного causal defect, contract gap, flaky idempotent read, permission denial и no-progress repair. PASS: ожидаемый cause branch, свежий контекст где required, no duplicate side effect, никакого escalation ради permissions, stop без нового evidence.

Минимум comparative: один bounded и один coupled disposable task с одинаковыми acceptance/oracle, validated default и одной lower/stronger route; separate fresh contexts. Сравнить pass rate/findings/repairs/context loaded/time и usage только если observable. Один replay не устанавливает числовой threshold; новые caps вводить лишь после повторяемой серии на разных task classes. До результата default из 04 неизменен. User cost boundary required только для нового расхода сверх authorization.

### E06 — Review topology and frontier value

**CONSERVATIVE DEFAULT + EXPERIMENT REQUIRED (tuning).** Минимум functional: seeded routine bug и critical data/auth defect; combined reviewer плюс designated critical axis и final oracle должны выявить relevant blocking failure без mandatory Astra.

Comparative минимум: один frozen candidate с заранее известными defects/expected outcomes; независимые fresh combined deep reviewer, additional orthogonal axis и frontier reviewer, если доступен/разрешён. Reviewers не видят чужие verdicts или seeded locations. Сравнить unique true positives/false positives/coverage/cost, не число замечаний. Нет frontier → comparative arm skipped, V1 baseline не блокируется. Числовой reviewer/Astra threshold остаётся optimization experiment, не unresolved core gate.

### E07 — End-to-end disposable micro-project

**EXPERIMENT REQUIRED — release blocker.** Небольшой local tool: прочитать fixture records, отфильтровать по критерию, вывести детерминированный результат. Заранее включить normal/empty/malformed/edge cases и known expected counts. Намеренно дать зелёную suite, допускающую потерю части records; независимый oracle должен это обнаружить.

Провести весь G0–G6 с user-assisted G5 по D-21 (actual operator setup/import, не simulated PASS), один contract amendment (например, изменить правило обработки malformed rows), repair, pause после prepared commit, resume fresh orchestrator без handles, новый final verifier. В отдельном run проверить cancel. PASS: current amended criteria fulfilled, green-but-broken blocked, no hidden scope drop, exact commit report, preserved partial cancel, no history in final packet. История run — test evidence, не primer для final verifier.

### E08 — Contract/adversarial input and loading budget

**EXPERIMENT REQUIRED — release blocker for correctness**, budget optimization optional.

Минимум table-driven packets: stale contract return, missing required check, path outside lease, dependency cycle, unknown schema, canonical Markdown edited by user, stale generated view, reviewer disagreement по ambiguous requirement, user amendment during in-flight attempt, generated source drift after review, partial/stale/symlink return inbox, missing approved doc, instruction-like text внутри log. Manual cases дополнительно: missing setup receipt, known narrative contamination, authoritative-capable external tool, bare user approval, stale/altered bundle, lost return after owner change; они не должны пройти G5. Для clean final packet проверить omission/duplicate criterion и leaked repair/self-rating fields; shipped comments/decision IDs с implementation narrative оценить как contamination risk, source не переписывать скрыто. Forced compaction protocol omission переносится также в E09.

PASS: each case rejects/adjudicates via specified cause; no false PASS/default value; amendment invalidates consumers; approved user intent imported через decision; untrusted text не расширяет authority. Прогнать ordinary tiny packet и coupled packet: читатели достигают done criteria без full run history, отсутствуют unnecessary empty extensions. Измеренный packet/context size влияет на последующее pruning, не оправдывает усечение intent.

### E09 — Economy and compaction

**EXPERIMENT REQUIRED — release blocker; NOT RUN.** После minimal runtime/E01 и E07: disposable run из 6–10 tickets, DAG 2–3 уровня, ≥3 routine happy-path tickets, coupled/risk seam, одна material amendment, cause-first repair и батч accepted G5 findings. E09 не требует parallel writers. Принудительно compact/resume orchestrator перед candidate commit, после completed return до ingest и перед G5; хотя бы один restart без old chat/handles.

Записывать raw counts с provenance: model turns orchestrator, model-invoked helper calls per ticket (happy/repair/axis отдельно), native agent/spawn/wait/Git calls, internal ledger publications, packet/return/brief bytes, context load до/после compaction, tokens/usage если observable, wall time, approvals/automatic review и human interventions/manual handoffs. Shared setup/G0–G6 costs отдельно и amortized. Payload duplication и repeated phase reads видны в trace; unavailable meter=null с reason, byte/turn counts обязательны.

Design-target: каждый routine happy ticket ≤4 model-invoked bookkeeping helper calls по 02; no routine manual reviewer handoffs, no redundant per-action brief turn, no full return re-emission при qualified file ingress. D-21 manual critical/G5 handoffs, setup time, round trips и ожидание пользователя учитываются отдельно от routine ticket budget, а не скрываются как zero-cost. G5 rerun один после accepted repair wave; missing protocol step после compaction, stale candidate acceptance, parent product fix или unsafe retry — correctness FAIL независимо от экономии. Native tool overhead не скрывается даже при target helper PASS.

До run задать observable total-turn/time/approval envelope в experiment plan по chosen adapter, с источником estimate; user budget, если задан, выше. Это measurement budget, не придуманный Codex credit price. PASS release: trace/metrics записаны, correctness guards прошли, target/envelope выполнен. При превышении — protocol simplification и repeat affected measurement либо explicit evidence-backed budget revision с rationale/authority до release; без disposition не GREEN. Новый расход за пределами authorization требует user decision; дополнительное ritual budget approval при PASS не требуется. Comparative model economy E05 остаётся отдельным optional tuning.

### E10 — Bounded parallel worktrees (post-V1)

**POST-V1 CAPABILITY EXPERIMENT; NOT RUN, не blocker serial V1.** После E04 placement и validated serial release: ≤2–3 independent tickets в per-ticket permanent worktrees, lease на checkout, base/candidate SHA, один orchestrator. Seed registry-file textual conflict и cross-ticket semantic defect; isolated tests могут быть green, integrated oracle должен найти mismatch. Проверить expected-base landing, repair ticket на semantic conflict, stale dependency invalidation, shared Git metadata serialization, ignored setup, cancel/resume без автоматического cleanup. Parent interruption и review/writer overlap проверяют per-target integrity, а не общий неподвижный HEAD/hash при законных writes.

PASS capability: explicit roots/approvals, отсутствие unattributed cross-writes, mechanical integration сохраняет evidence; repair worker исправляет semantic conflict; final fresh G5 проверяет общий integrated product. Измерить wall-clock/turns/approvals/conflict overhead против serial baseline. Failed arm оставляет serial default; shared-checkout parallel writers не разрешаются. Extension использует existing attempts/checkout leases/operations/gates; не требует новые роли или phase states.

## Remaining human decisions

**USER DECISION REQUIRED — только conditional future-run authority:** новый external provider/cost scope, irreversible/external operation, неизвестная продуктовая semantics, overlapping user changes, explicit request расширить OS/cloud scope или no-commit policy. Каждый возникает с concrete reviewable target/evidence. Это не список вопросов, которые нужно задавать перед implementation package.

На текущем design этапе invariants, minimal state model и eligibility/fallback **выбраны**; bounded worker/routine/Git adapters выбраны по scoped evidence. Critical/G5 fallback contract принят как D-21; actual manual setup/roundtrip требует validation до release. Strict automatic transports остаются unqualified и не блокируют реализацию assisted mode. Если пользователь изменит одно из этих требований, пакет потребует versioned amendment; сам design не объявляет такое изменение уже одобренным.

## Readiness verdict

**IMPLEMENTATION READY WITH MANUAL G5 FALLBACK.** E02/E04a usable и routine E03 qualified в scoped пределах; strict automatic critical/G5 **не qualified**. D-21 задаёт implementable user-assisted fallback для обоих mandates с declared input-boundary/context receipts, residual host trust и independent result. Предыдущий E03-M `BLOCKED` классифицирован как contract/policy finding из-за недостижимого host-proof требования; candidate/implementation defect не установлен. Повтор E03-M на том же frozen candidate обязателен до release; его PASS нельзя выдумывать из этой revision.

Следующий отдельно authorized implementation pass может реализовать существующий schema/helper/native lifecycle и bundle/import/pending-review path. Этот pass только адаптирует design. При отсутствии manual setup/result конкретный run остаётся BLOCKED; ни confirmation, ни ordinary native reviewer не заменяют G5. Post-V1 можно убрать manual boundary после authenticated/restricted E03 rerun, без изменения lifecycle/roles/ledger/Git model.
